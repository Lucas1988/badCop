import os
import base64
import logging
from pathlib import Path
from typing import Any
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
import time
import secrets
import io
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("interrogation_app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def _get_base64_video(video_path: Path) -> str:
    """
    Read the video file and return a base64-encoded data URL string.

    :param video_path: Path to the mp4 loop video on disk
    :return: Data URL for inline <video> playback
    """
    logger.debug(f"Encoding video file: {video_path}")
    video_bytes: bytes = video_path.read_bytes()
    b64: str = base64.b64encode(video_bytes).decode("utf-8")
    return f"data:video/mp4;base64,{b64}"


def _get_base64_audio(audio_path: Path) -> str:
    """
    Read the audio file and return a base64-encoded data URL string.

    :param audio_path: Path to tension.mp3
    :return: Data URL for inline <audio> playback
    """
    logger.debug(f"Encoding audio file: {audio_path}")
    audio_bytes: bytes = audio_path.read_bytes()
    b64: str = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:audio/mpeg;base64,{b64}"


def _resize_input_reference(image_path: Path, size: str) -> io.BytesIO:
    """
    Resize or crop the input image to match the target video size.

    :param image_path: Full path to police_officer_drawing.png
    :param size: Target resolution string like '1280x720'
    :return: BytesIO containing a JPEG with .name and .mime_type set
    """
    width_str, height_str = size.split("x")
    width = int(width_str)
    height = int(height_str)

    img = Image.open(image_path).convert("RGB")
    img_ratio = img.width / img.height
    target_ratio = width / height

    if img_ratio > target_ratio:
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        img = img.crop((0, top, img.width, top + new_height))

    img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    buf.name = "input.jpg"
    buf.mime_type = "image/jpeg"
    return buf


def _generate_officer_video(spoken_text: str) -> str | None:
    """
    Generate a short Sora-2 clip of the interrogation officer delivering the given line.

    :param spoken_text: The line the officer should 'say'
    :return: A base64 data URL string for the resulting MP4 clip, or None on failure
    """
    openai_api_key: str | None = "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"

    client = OpenAI(api_key=openai_api_key)

    size: str = "1280x720"
    still_frame_path: Path = Path().joinpath("police_officer.jpg")
    if not still_frame_path.exists():
        logger.error("Image not found, cannot create Sora clip.")
        return None

    # Prepare reference frame for Sora
    input_image: io.BytesIO = _resize_input_reference(still_frame_path, size)

    # Build prompt for Sora
    sora_prompt: str = (
        "Cinematic interrogation room. Dim overhead lamp. The camera faces a stern police officer "
        "sitting at a table, eye contact with the viewer like first-person interrogation. "
        "The officer delivers the following line slowly and clearly, with minimal head movement, "
        "mouth synced, calm but firm:\n\n"
        f"\"{spoken_text}\""
    )

    logger.info("Starting Sora video generation for officer line.")
    video_job: Any = client.videos.create(
        model="sora-2",
        prompt=sora_prompt,
        input_reference=input_image,
        seconds="4",
        size=size,
    )

    job_id: str = getattr(video_job, "id", secrets.token_hex(6))
    status: str = str(getattr(video_job, "status", "unknown")).lower()
    logger.info(f"Sora job submitted: id={job_id} status={status}")

    terminal_statuses = {
        "succeeded",
        "completed",
        "failed",
        "cancelled",
        "canceled",
        "error",
    }

    shown_status: str | None = None
    while status not in terminal_statuses:
        time.sleep(2)
        video_job = client.videos.retrieve(job_id)
        status = str(getattr(video_job, "status", "unknown")).lower()
        progress = getattr(video_job, "progress", None)
        pct = float(progress) if isinstance(progress, (int, float)) else 0.0

        if status != shown_status or int(pct) % 5 == 0:
            logger.info(
                f"Sora progress | id={job_id} status={status} progress={pct:.1f}%"
            )
            shown_status = status

    if status in {"failed", "error", "cancelled", "canceled"}:
        error_msg = getattr(getattr(video_job, "error", None), "message", None)
        logger.error(
            f"Sora job failed id={job_id} status={status} error={error_msg}"
        )
        return None

    logger.info(f"Sora job finished id={job_id} status={status}")
    mp4_content: Any = client.videos.download_content(job_id, variant="video")

    random_filename: str = f"{secrets.token_hex(6)}.mp4"
    mp4_path: Path = Path().joinpath(random_filename)
    mp4_content.write_to_file(mp4_path)
    logger.info(f"Sora clip saved to {mp4_path}")

    # Also return base64 so we can inline-play it immediately in the browser
    mp4_bytes: bytes = mp4_path.read_bytes()
    b64_clip: str = base64.b64encode(mp4_bytes).decode("utf-8")
    return f"data:video/mp4;base64,{b64_clip}"


def _render_scene(loop_video_src: str, audio_src: str | None, talk_video_src: str | None) -> None:
    """
    Render the scene so the talking clip begins right after the current loop finishes.
    Background music is unaffected. The talking clip is strictly one-shot per render.
    """
    logger.debug("Rendering scene iframe with one-shot talking clip.")

    audio_block: str = ""
    if audio_src is not None:
        audio_block = f"""
        <audio id="bgAudio" loop style="display:none">
            <source src="{audio_src}" type="audio/mpeg">
        </audio>
        <div id="musicBtn" class="music-btn" title="Toggle music">🎵</div>
        """

    talk_block: str = ""
    if talk_video_src:
        talk_block = f"""
        <video id="talkVideo" preload="auto" playsinline style="display:none">
            <source src="{talk_video_src}" type="video/mp4">
        </video>
        """

    html_doc: str = f"""
    <html>
    <head>
      <style>
        body {{
          margin: 0; background-color: black; color: white; font-family: system-ui, sans-serif;
          display: flex; flex-direction: column; align-items: center; justify-content: flex-start; height: 100vh; padding-top: 20px;
        }}
        .video-stage {{ position: relative; display: inline-block; transform: scale(0.5); transform-origin: top center; }}
        .video-inner {{ position: relative; }}
        #loopVideo {{ display: block; width: 130%; height: auto; }}
        #talkVideo {{ position: absolute; inset: 0; width: 130%; height: 100%; object-fit: cover; background-color: black; }}
        .music-btn {{
          position: fixed; top: 50px; right: 25px; z-index: 9999; width: 48px; height: 48px; border-radius: 50%;
          background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
          display: flex; align-items: center; justify-content: center; cursor: pointer;
        }}
        .music-btn.active {{ background-color: rgba(255,255,255,0.4); }}
      </style>
    </head>
    <body>
      <div class="video-stage">
        <div class="video-inner">
          <video id="loopVideo" autoplay loop muted playsinline>
            <source src="{loop_video_src}" type="video/mp4">
          </video>
          {talk_block}
        </div>
      </div>

      {audio_block}

      <script>
      // Music toggle (no forced restarts)
      const btn = document.getElementById("musicBtn");
      const audio = document.getElementById("bgAudio");
      if (btn && audio) {{
        audio.volume = 0.15;
        const stored = localStorage.getItem("musicEnabled") === "1";
        if (stored) {{ btn.classList.add("active"); audio.play().catch(()=>{{}}); }}
        btn.addEventListener("click", () => {{
          const active = btn.classList.toggle("active");
          localStorage.setItem("musicEnabled", active ? "1" : "0");
          if (active) audio.play().catch(()=>{{}}); else audio.pause();
        }});
      }}

      const talkVid = document.getElementById("talkVideo");
      const loopVid = document.getElementById("loopVideo");

      if (talkVid && loopVid) {{
        // --- ONE-SHOT GATE ---
        let canPlayOnce = true;      // allow exactly one playback per render
        let talkReady = false;
        let talkStarted = false;
        let pendingBoundary = false;
        const boundaryThreshold = 0.5; // seconds
        let pollId = null;

        loopVid.style.visibility = "visible";

        // Autoplay-friendly start: begin muted, unmute on playing
        talkVid.muted = true;
        talkVid.playsInline = true;

        talkVid.addEventListener("canplaythrough", () => {{ talkReady = true; }});
        talkVid.addEventListener("playing", () => {{
          setTimeout(() => {{ talkVid.muted = false; }}, 30);
        }});

        function armBoundaryStart() {{
          function checkBoundary() {{
            if (!canPlayOnce) return;          // stop after first run
            if (!loopVid.duration || isNaN(loopVid.duration)) return;
            if (!talkReady || talkStarted) return;
            const remaining = loopVid.duration - loopVid.currentTime;
            if (remaining > 0 && remaining <= boundaryThreshold) {{
              if (loopVid.hasAttribute("loop")) loopVid.removeAttribute("loop");
              pendingBoundary = true;
            }}
          }}
          loopVid.addEventListener("timeupdate", checkBoundary);
          if (pollId) clearInterval(pollId);
          pollId = setInterval(checkBoundary, 60);
        }}

        loopVid.addEventListener("ended", () => {{
          if (pendingBoundary && !talkStarted && canPlayOnce) {{
            pendingBoundary = false;
            loopVid.style.visibility = "hidden";
            talkVid.style.display = "block";
            talkVid.currentTime = 0;
            talkVid.play().then(() => {{ talkStarted = true; }}).catch(() => {{}});
          }} else {{
            loopVid.play().catch(()=>{{}});
          }}
        }});

        talkVid.addEventListener("ended", () => {{
          // Teardown so it cannot play again until a new render provides a new talkVideo
          canPlayOnce = false;
          talkStarted = false;
          pendingBoundary = false;
          if (pollId) {{ clearInterval(pollId); pollId = null; }}

          talkVid.pause();
          try {{
            const src = talkVid.querySelector('source');
            if (src) src.removeAttribute('src');
            talkVid.removeAttribute('src');
            talkVid.load();
          }} catch(e) {{}}

          talkVid.style.display = "none";
          loopVid.style.visibility = "visible";
          loopVid.setAttribute("loop", "");
          loopVid.play().catch(()=>{{}});
        }});

        armBoundaryStart();
      }}
      </script>
    </body>
    </html>
    """

    components.html(html_doc, height=600, scrolling=False)



def _ensure_session() -> None:
    """
    Initialize Streamlit session state for messages and last generated officer clip.

    :return: None
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []
        logger.info("Session message state initialized.")

    if "officer_clip_b64" not in st.session_state:
        st.session_state.officer_clip_b64 = None
        logger.info("Session video clip state initialized.")


def _append_user_message(text: str) -> None:
    """
    Append a user message to chat history.

    :param text: The user's message text
    :return: None
    """
    st.session_state.messages.append({"role": "user", "content": text})
    logger.info(f"User message: {text}")


def _append_assistant_message(text: str) -> None:
    """
    Append assistant message to chat history.

    :param text: The assistant's message text
    :return: None
    """
    st.session_state.messages.append({"role": "assistant", "content": text})
    logger.info(f"Assistant reply logged: {text}")


def _render_history() -> None:
    """
    Render the chat history using Streamlit chat components.

    :return: None
    """
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])


def _get_officer_reply_and_clip(
    user_text: str, history: list[dict[str, str]]
) -> tuple[str, str | None]:
    """
    Get a GPT-5-nano interrogation reply and generate a matching Sora-2 talking clip.

    :param user_text: Latest suspect input
    :param history: Chat history so far
    :return: Tuple of (reply text, base64 video clip URL or None)
    """
    system_preamble: str = (
        "You are a seasoned police officer conducting a formal interrogation. "
        "You are questioning a suspect about breaking into the Louvre and stealing the Mona Lisa. "
        "Your tone is calm, professional, and precise. "
        "Keep answers short, serious, and under 20 words. "
        "Ask pointed follow-up questions about times, methods, and accomplices."
    )

    messages_for_llm: list[dict[str, str]] = [{"role": "system", "content": system_preamble}]
    messages_for_llm.extend(history)
    messages_for_llm.append({"role": "user", "content": user_text})

    openai_api_key: str | None = "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"

    client = OpenAI(api_key=openai_api_key)
    model_name: str = os.environ.get("MODEL_NAME", "gpt-5-nano")

    logger.info(f"Sending prompt to model '{model_name}' with {len(messages_for_llm)} messages.")

    try:
        resp: Any = client.chat.completions.create(
            model=model_name,
            messages=messages_for_llm,
        )
        reply_text: str = resp.choices[0].message.content.strip()
        logger.info(f"Model response: {reply_text}")
    except Exception as e:
        logger.exception("Error calling GPT model:")
        return (
            f"Error contacting interrogation system: {e}",
            None,
        )

    # Generate Sora-2 clip for this reply
    clip_b64: str | None = _generate_officer_video(reply_text)

    return reply_text, clip_b64


def main() -> None:
    """
    Run the interrogation Streamlit app.

    :return: None
    """
    st.set_page_config(page_title="Interrogation Chat", page_icon="🕵️", layout="wide")

    # Chat bar positioning and dark theme
    st.markdown(
        """
        <style>
        :root { --chat-offset: 120px; }
        body { background-color: black; }
        .block-container { padding-top: 0; padding-bottom: 0; background-color: black; }
        [data-testid="stChatInput"] {
            position: fixed;
            left: 0;
            width: 100%;
            bottom: var(--chat-offset);
            z-index: 999999;
            background-color: rgba(0,0,0,0.9);
            border-top: 1px solid rgba(255,255,255,0.1);
            padding: 0.5rem 1rem !important;
        }
        [data-testid="stChatInput"] textarea {
            background-color: rgb(20,20,20) !important;
            color: #fff !important;
            border: 1px solid rgba(255,255,255,0.2) !important;
        }
        footer, [data-testid="stStatusWidget"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _ensure_session()

    loop_path: Path = Path().joinpath("police_officer.mp4")
    audio_path: Path = Path().joinpath("tension.mp3")

    if loop_path.exists():
        loop_src: str = _get_base64_video(loop_path)
    else:
        st.error("Video file not found (expected 'police_officer.mp4').")
        loop_src = ""

    audio_src: str | None = _get_base64_audio(audio_path) if audio_path.exists() else None

    _render_scene(loop_src, audio_src, st.session_state.officer_clip_b64)

    _render_history()

    user_input: str | None = st.chat_input("Type your message...")
    if user_input:
        _append_user_message(user_input)

        with st.chat_message("assistant"):
            reply_text, clip_src = _get_officer_reply_and_clip(
                user_input,
                st.session_state.messages[:-1],
            )
            st.markdown(reply_text)

        _append_assistant_message(reply_text)

        # Store latest speaking clip (may be None)
        st.session_state.officer_clip_b64 = clip_src
        logger.info(
            f"Updated session officer_clip_b64 set: {clip_src is not None}"
        )

        # Force a rerender so the new clip (if any) shows immediately
        st.rerun()


if __name__ == "__main__":
    main()
