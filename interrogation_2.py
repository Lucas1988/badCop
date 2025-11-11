import os
import base64
import logging
from pathlib import Path
from typing import Any
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
import secrets
import json
import requests
from dotenv import load_dotenv

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

load_dotenv()


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

    :param audio_path: Path to tension.mp3 or generated officer speech
    :return: Data URL for inline <audio> playback
    """
    logger.debug(f"Encoding audio file: {audio_path}")
    audio_bytes: bytes = audio_path.read_bytes()
    b64: str = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:audio/mpeg;base64,{b64}"


def _render_scene(
        default_loop_video_src: str,
        emotion_loop_video_src: str | None,
        bg_audio_src: str | None,
        speech_audio_src: str | None,
) -> None:
    """
    Render the scene with a default looping interrogation video, an optional emotion-based
    loop video that is only shown while the speech audio plays, optional background music,
    and an optional one-shot speech audio clip for the latest reply.

    :param default_loop_video_src: Base64 data URL for the default loop video
    :param emotion_loop_video_src: Base64 data URL for the emotion-specific loop video, or None
    :param bg_audio_src: Base64 data URL for background music, or None
    :param speech_audio_src: Base64 data URL for officer speech audio, or None
    :return: None
    """
    logger.debug("Rendering scene iframe with emotion-based loop video and speech audio.")

    bg_audio_block: str = ""
    if bg_audio_src is not None:
        bg_audio_block = f"""
        <audio id="bgAudio" loop style="display:none">
            <source src="{bg_audio_src}" type="audio/mpeg">
        </audio>
        <div id="musicBtn" class="music-btn" title="Toggle music">🎵</div>
        """

    speech_block: str = ""
    if speech_audio_src is not None:
        speech_block = f"""
        <audio id="speechAudio" autoplay style="display:none">
            <source src="{speech_audio_src}" type="audio/mpeg">
        </audio>
        """

    emotion_video_block: str = ""
    if emotion_loop_video_src is not None:
        emotion_video_block = f"""
          <video id="emotionVideo" autoplay loop muted playsinline style="position:absolute; top:0; left:0; width:130%; height:auto; display:none;">
            <source src="{emotion_loop_video_src}" type="video/mp4">
          </video>
        """

    html_doc: str = f"""
    <html>
    <head>
      <style>
        body {{
          margin: 0;
          background-color: black;
          color: white;
          font-family: system-ui, sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: flex-start;
          height: 100vh;
          padding-top: 20px;
        }}
        .video-stage {{
          position: relative;
          display: inline-block;
          transform: scale(0.5);
          transform-origin: top center;
        }}
        .video-inner {{
          position: relative;
          overflow: hidden;
        }}
        #defaultVideo {{
          display: block;
          width: 130%;
          height: auto;
        }}
        .music-btn {{
          position: fixed;
          top: 80px;
          right: 25px;
          z-index: 9999;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: rgba(255,255,255,0.1);
          border: 1px solid rgba(255,255,255,0.3);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        }}
        .music-btn.active {{
          background-color: rgba(255,255,255,0.4);
        }}
      </style>
    </head>
    <body>
      <div class="video-stage">
        <div class="video-inner">
          <video id="defaultVideo" autoplay loop muted playsinline>
            <source src="{default_loop_video_src}" type="video/mp4">
          </video>
          {emotion_video_block}
        </div>
      </div>

      {bg_audio_block}
      {speech_block}

    <script>
    const btn = document.getElementById("musicBtn");
    const audio = document.getElementById("bgAudio");
    const defaultVideo = document.getElementById("defaultVideo");
    const emotionVideo = document.getElementById("emotionVideo");
    const speechAudio = document.getElementById("speechAudio");

    function showDefaultVideo() {{
      if (defaultVideo) {{
        defaultVideo.style.display = "block";
      }}
      if (emotionVideo) {{
        emotionVideo.style.display = "none";
      }}
    }}

    function showEmotionVideo() {{
      if (!emotionVideo) {{
        return;
      }}
      emotionVideo.style.display = "block";
      if (defaultVideo) {{
        defaultVideo.style.display = "none";
      }}
    }}

    // Initial state: default video visible
    showDefaultVideo();

    if (speechAudio) {{
      speechAudio.addEventListener("play", () => {{
        if (emotionVideo) {{
          showEmotionVideo();
        }}
      }});

      const backToDefault = () => {{
        showDefaultVideo();
      }};

      speechAudio.addEventListener("ended", backToDefault);
      speechAudio.addEventListener("pause", () => {{
        if (speechAudio.duration && (speechAudio.currentTime >= speechAudio.duration - 0.1)) {{
          backToDefault();
        }}
      }});
    }}

    if (btn && audio) {{
      audio.volume = 0.15;

      // Default OFF unless explicitly enabled before
      const stored = localStorage.getItem("musicEnabled");
      const enabled = stored === "1";

      if (enabled) {{
        btn.classList.add("active");
        audio.play().catch(() => {{}});
      }} else {{
        btn.classList.remove("active");
        audio.pause();
      }}

      btn.addEventListener("click", () => {{
        const nowEnabled = btn.classList.toggle("active");
        localStorage.setItem("musicEnabled", nowEnabled ? "1" : "0");
        if (nowEnabled) {{
          audio.play().catch(() => {{}});
        }} else {{
          audio.pause();
        }}
      }});
    }}
    </script>

    </body>
    </html>
    """

    components.html(html_doc, height=600, scrolling=False)


def _ensure_session() -> None:
    """
    Initialize Streamlit session state for messages and media.

    :return: None
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []
        logger.info("Session message state initialized.")

    if "emotion_loop_b64" not in st.session_state:
        st.session_state.emotion_loop_b64 = None
        logger.info("Session emotion-based loop video state initialized.")

    if "speech_audio_b64" not in st.session_state:
        st.session_state.speech_audio_b64 = None
        logger.info("Session speech audio state initialized.")

    if "pending_user_input" not in st.session_state:
        st.session_state.pending_user_input = None


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


def _generate_officer_audio(spoken_text: str) -> Path | None:
    """
    Generate an ElevenLabs audio clip of the interrogation officer delivering the given line.

    :param spoken_text: The line the officer should speak
    :return: Path to the generated MP3 file, or None on failure
    """
    api_key: str | None = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        logger.error("ELEVENLABS_API_KEY is not set, cannot generate officer audio.")
        return None

    voice_id: str = "VMEiS9pN5WcJdwYFOr4i"
    url: str = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    payload: dict[str, Any] = {
        "text": spoken_text,
        "model_id": "eleven_v3",
    }

    headers: dict[str, str] = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    try:
        logger.info("Calling ElevenLabs TTS API for officer audio.")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except Exception as exc:
        logger.exception(f"Error while calling ElevenLabs TTS API: {exc}")
        return None

    filename: Path = Path().joinpath(f"{secrets.token_hex(6)}.mp3")
    filename.write_bytes(response.content)
    logger.info(f"Generated officer audio saved to {filename}")
    return filename


def _choose_loop_video_for_emotion(emotion: str) -> Path | None:
    """
    Choose a random loop video for the given emotion from the static folder.

    :param emotion: Emotion label such as 'angry', 'sad', or 'neutral'
    :return: Path to a matching MP4 file, or None if no match is found
    """
    static_dir: Path = Path().joinpath("static")
    if not static_dir.exists():
        logger.error(f"Static directory not found: {static_dir}")
        return None

    # 1. Try emotion-specific videos
    pattern: str = f"officer_{emotion}*.mp4"
    matches: list[Path] = list(static_dir.glob(pattern))

    # 2. If no emotion matches → try neutral variants
    if not matches:
        logger.warning(
            f"No videos found for emotion '{emotion}', trying neutral variants."
        )
        matches = list(static_dir.glob("officer_neutral.mp4"))

    # 3. If still nothing → fallback to specific neutral file
    if not matches:
        fallback: Path = static_dir.joinpath("officer_neutral.mp4")
        if fallback.exists():
            logger.warning(
                f"No variant videos found. Falling back to single '{fallback}'."
            )
            return fallback

        logger.error("No suitable loop videos found for any emotion.")
        return None

    # 4. If matches exist → choose a random one
    chosen: Path = secrets.choice(matches)
    logger.info(f"Chosen loop video for emotion '{emotion}': {chosen}")
    return chosen


def _get_officer_reply_and_audio(
        user_text: str, history: list[dict[str, str]]
) -> tuple[str, str, str | None]:
    """
    Get a GPT-5-nano interrogation reply as JSON with text and emotion,
    then synthesize the spoken line with ElevenLabs. Uses streaming so that
    the raw JSON is logged as it becomes available.

    :param user_text: Latest suspect input
    :param history: Chat history so far
    :return: Tuple of (reply text for display and TTS, emotion label, base64 audio or None)
    """
    system_preamble: str = (
        "You are a seasoned police officer conducting a formal interrogation. "
        "You are questioning a suspect about breaking into the Louvre and stealing the Mona Lisa. "
        "Your tone is calm, professional, and precise. "
        "Keep answers short, serious, and under 20 words. "
        "Ask pointed follow-up questions about times, methods, and accomplices. "
        "Respond strictly as a JSON object with the following structure: "
        '{"text": "<officer reply including expressive tags like <sigh>, <angry>, <giggles>, etc.>", '
        '"emotion": "angry|sad|neutral"}. '
        "Pick 'angry' when you are confronting lies or contradictions, 'sad' when expressing disappointment, "
        "and 'neutral' for matter-of-fact questioning."
    )

    messages_for_llm: list[dict[str, str]] = [{"role": "system", "content": system_preamble}]
    messages_for_llm.extend(history)
    messages_for_llm.append({"role": "user", "content": user_text})

    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY is not set, cannot contact GPT model.")
        error_text: str = "Interrogation system is unavailable due to missing configuration."
        return error_text, "neutral", None

    client = OpenAI(api_key=openai_api_key)
    model_name: str = os.environ.get("MODEL_NAME", "gpt-5-nano")

    logger.info(
        f"Sending prompt to model '{model_name}' with {len(messages_for_llm)} messages (streaming enabled)."
    )

    try:
        streamed_chunks: list[str] = []
        stream: Any = client.chat.completions.create(
            model=model_name,
            messages=messages_for_llm,
            response_format={"type": "json_object"},
            stream=True,
        )

        for chunk in stream:
            delta_content: str | None = None
            choice = chunk.choices[0] if chunk.choices else None
            if choice and choice.delta and choice.delta.content:
                delta_content = choice.delta.content
            if delta_content:
                streamed_chunks.append(delta_content)
                logger.info(f"Streaming chunk: {delta_content}")

        raw_content: str = "".join(streamed_chunks).strip()
        logger.info(f"Full streamed model JSON response: {raw_content}")
        parsed: dict[str, Any] = json.loads(raw_content)
        reply_text: str = str(parsed.get("text", "")).strip()
        emotion: str = str(parsed.get("emotion", "neutral")).strip().lower()
        if emotion not in {"angry", "sad", "neutral"}:
            logger.warning(f"Unexpected emotion '{emotion}' from model, normalizing to 'neutral'.")
            emotion = "neutral"
        logger.info(f"Model response text: {reply_text} | emotion: {emotion}")
    except Exception as exc:
        logger.exception(f"Error calling GPT model: {exc}")
        error_text = f"Error contacting interrogation system: {exc}"
        return error_text, "neutral", None

    audio_path: Path | None = _generate_officer_audio(reply_text)
    if audio_path is None:
        return reply_text, emotion, None

    audio_b64: str = _get_base64_audio(audio_path)
    return reply_text, emotion, audio_b64


def main() -> None:
    """
    Run the interrogation Streamlit app.

    :return: None
    """
    st.set_page_config(page_title="Interrogation Chat", page_icon="🕵️", layout="wide")

    st.markdown(
        """
        <style>
        :root { --chat-offset: 220px; }
        body { background-color: black; }
        .block-container {
            padding-top: 0;
            padding-bottom: 260px;
            background-color: black;
        }
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
        [data-testid="stChatMessageList"] {
            padding-bottom: 260px !important;
        }
        footer, [data-testid="stStatusWidget"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _ensure_session()

    default_loop_path: Path = Path().joinpath("static/police_officer.mp4")
    bg_audio_path: Path = Path().joinpath("static/tension.mp3")

    if not default_loop_path.exists():
        st.error("Video file not found (expected 'static/police_officer.mp4').")
        default_loop_src: str = ""
    else:
        default_loop_src = _get_base64_video(default_loop_path)

    bg_audio_src: str | None = _get_base64_audio(bg_audio_path) if bg_audio_path.exists() else None
    emotion_loop_src: str | None = st.session_state.emotion_loop_b64
    speech_audio_src: str | None = st.session_state.speech_audio_b64

    # Chat input first so the new user message appears immediately in history
    user_input: str | None = st.chat_input("Type your message...")
    if user_input:
        _append_user_message(user_input)
        st.session_state.pending_user_input = user_input

    if default_loop_src:
        _render_scene(
            default_loop_video_src=default_loop_src,
            emotion_loop_video_src=emotion_loop_src,
            bg_audio_src=bg_audio_src,
            speech_audio_src=speech_audio_src,
        )

    _render_history()

    if st.session_state.pending_user_input:
        latest_user_text: str = st.session_state.pending_user_input

        with st.chat_message("assistant"):
            reply_text, emotion, speech_audio_b64 = _get_officer_reply_and_audio(
                latest_user_text,
                st.session_state.messages[:-1],
            )
            st.markdown(reply_text)

        _append_assistant_message(reply_text)

        st.session_state.speech_audio_b64 = speech_audio_b64

        emotion_video_path: Path | None = _choose_loop_video_for_emotion(emotion)
        if emotion_video_path is not None:
            try:
                st.session_state.emotion_loop_b64 = _get_base64_video(emotion_video_path)
            except Exception as exc:
                logger.exception(f"Failed to encode emotion loop video '{emotion_video_path}': {exc}")

        logger.info(
            f"Updated session speech_audio_b64 set: {speech_audio_b64 is not None}"
        )

        st.session_state.pending_user_input = None
        st.rerun()


if __name__ == "__main__":
    main()
