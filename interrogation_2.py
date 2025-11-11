import os
import base64
import logging
from pathlib import Path
from typing import Any, Optional
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
    logger.info(f"Encoding video file: {video_path}")
    video_bytes: bytes = video_path.read_bytes()
    b64: str = base64.b64encode(video_bytes).decode("utf-8")
    return f"data:video/mp4;base64,{b64}"


def _get_base64_audio(audio_path: Path) -> str:
    """
    Read the audio file and return a base64-encoded data URL string.

    :param audio_path: Path to tension.mp3 or generated officer speech
    :return: Data URL for inline <audio> playback
    """
    logger.info(f"Encoding audio file: {audio_path}")
    audio_bytes: bytes = audio_path.read_bytes()
    b64: str = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:audio/mpeg;base64,{b64}"


def _render_scene(
        default_loop_video_src: str,
        emotion_loop_video_src: Optional[str],
        bg_audio_src: Optional[str],
        speech_audio_src: Optional[str],
) -> None:
    """
    Render the scene using a single video element that switches between the default
    interrogation loop and an optional emotion-specific loop while the speech audio plays.

    :param default_loop_video_src: Base64 data URL or file URL for the default loop video
    :param emotion_loop_video_src: Base64 data URL or file URL for the emotion-specific loop video, or None
    :param bg_audio_src: Base64 data URL or file URL for background music, or None
    :param speech_audio_src: Base64 data URL or file URL for officer speech audio, or None
    :return: None
    """
    logger.info("Rendering scene iframe with single video track and speech audio.")

    bg_audio_block: str = ""
    if bg_audio_src:
        bg_audio_block = f"""
        <audio id="bgAudio" loop style="display:none">
            <source src="{bg_audio_src}" type="audio/mpeg">
        </audio>
        <div id="musicBtn" class="music-btn" title="Toggle music">🎵</div>
        """

    speech_block: str = ""
    if speech_audio_src:
        speech_block = f"""
        <audio id="speechAudio" autoplay style="display:none">
            <source src="{speech_audio_src}" type="audio/mpeg">
        </audio>
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
          display: flex;
          justify-content: center;
          align-items: center;
          transform: scale(0.5);
          transform-origin: top center;
          width: 100%;
          height: auto;
        }}
        .video-inner {{
          position: relative;
          overflow: hidden;
          width: 130%;
          height: auto;
          display: flex;
          justify-content: center;
          align-items: center;
          background-color: black;
        }}
        #mainVideo {{
          position: relative;
          display: block;
          width: 100%;
          height: auto;
          max-width: 100%;
          max-height: 100%;
          object-fit: contain;
          object-position: center center;
          z-index: 1;
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
          <video id="mainVideo" autoplay loop muted playsinline>
            <source src="{default_loop_video_src}" type="video/mp4">
          </video>
        </div>
      </div>

      {bg_audio_block}
      {speech_block}

    <script>
    // Unlock autoplay for later use
    document.addEventListener("click", enableMedia);
    document.addEventListener("keydown", enableMedia);

    function enableMedia() {{
      const vids = document.querySelectorAll("video, audio");
      vids.forEach(v => {{
        try {{
          v.play().then(() => {{
            v.pause();
          }}).catch(() => {{}});
        }} catch (e) {{}}
      }});
      document.removeEventListener("click", enableMedia);
      document.removeEventListener("keydown", enableMedia);
    }}

    const btn = document.getElementById("musicBtn");
    const audio = document.getElementById("bgAudio");
    const mainVideo = document.getElementById("mainVideo");
    const speechAudio = document.getElementById("speechAudio");

    const defaultSrc = "{default_loop_video_src}";
    const emotionSrc = "{emotion_loop_video_src or ""}";

    function playDefaultLoop() {{
      if (!mainVideo || !defaultSrc) return;
      if (mainVideo.getAttribute("data-current") === "default") {{
        if (mainVideo.paused) {{
          mainVideo.play().catch(() => {{}});
        }}
        return;
      }}
      mainVideo.pause();
      if (mainVideo.firstElementChild && mainVideo.firstElementChild.tagName === "SOURCE") {{
        mainVideo.firstElementChild.setAttribute("src", defaultSrc);
      }} else {{
        mainVideo.setAttribute("src", defaultSrc);
      }}
      try {{
        mainVideo.load();
      }} catch (e) {{}}
      mainVideo.loop = true;
      mainVideo.muted = true;
      mainVideo.playsInline = true;
      mainVideo.setAttribute("data-current", "default");
      mainVideo.play().catch(() => {{}});
    }}

    function playEmotionLoop() {{
      if (!mainVideo || !emotionSrc) return;
      if (mainVideo.getAttribute("data-current") === "emotion") {{
        if (mainVideo.paused) {{
          mainVideo.play().catch(() => {{}});
        }}
        return;
      }}
      mainVideo.pause();
      if (mainVideo.firstElementChild && mainVideo.firstElementChild.tagName === "SOURCE") {{
        mainVideo.firstElementChild.setAttribute("src", emotionSrc);
      }} else {{
        mainVideo.setAttribute("src", emotionSrc);
      }}
      try {{
        mainVideo.load();
      }} catch (e) {{}}
      mainVideo.loop = true;
      mainVideo.muted = true;
      mainVideo.playsInline = true;
      mainVideo.setAttribute("data-current", "emotion");
      mainVideo.play().catch(() => {{}});
    }}

    // Initial state: default loop
    playDefaultLoop();

    if (speechAudio) {{
      const switchBackToDefault = () => {{
        playDefaultLoop();
      }};

      speechAudio.addEventListener("play", () => {{
        if (emotionSrc) {{
          playEmotionLoop();
        }} else {{
          playDefaultLoop();
        }}
      }});

      speechAudio.addEventListener("ended", switchBackToDefault);
      speechAudio.addEventListener("error", switchBackToDefault);
      speechAudio.addEventListener("abort", switchBackToDefault);

      speechAudio.addEventListener("pause", () => {{
        if (!speechAudio.duration) return;
        const remaining = speechAudio.duration - speechAudio.currentTime;
        if (remaining <= 0.05) {{
          switchBackToDefault();
        }}
      }});
    }}

    if (btn && audio) {{
      audio.volume = 0.15;

      // Ensure default is OFF
      if (localStorage.getItem("musicEnabled") === null) {{
          localStorage.setItem("musicEnabled", "0");
      }}

      const enabled = localStorage.getItem("musicEnabled") === "1";

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

    components.html(html_doc, height=420, scrolling=False)


def _ensure_session() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "emotion_loop_b64" not in st.session_state:
        st.session_state.emotion_loop_b64 = None
    if "speech_audio_b64" not in st.session_state:
        st.session_state.speech_audio_b64 = None
    if "pending_user_input" not in st.session_state:
        st.session_state.pending_user_input = None


def _append_user_message(text: str) -> None:
    st.session_state.messages.append({"role": "user", "content": text})
    logger.info(f"User message: {text}")


def _append_assistant_message(text: str) -> None:
    st.session_state.messages.append({"role": "assistant", "content": text})
    logger.info(f"Assistant reply logged: {text}")


def _render_history() -> None:
    """
    Render all chat messages in the Streamlit UI while removing stage-direction
    tags enclosed in square brackets.

    :return: None
    """
    import re

    for m in st.session_state.messages:
        cleaned: str = re.sub(r"\[.*?\]", "", m["content"]).strip()
        with st.chat_message(m["role"]):
            st.markdown(cleaned)



def _generate_officer_audio(spoken_text: str) -> Optional[Path]:
    """
    Generate officer speech using ElevenLabs and save as MP3.

    :param spoken_text: The officer's spoken line
    :return: Path to generated MP3 or None if failed
    """
    api_key: Optional[str] = os.environ.get("ELEVENLABS_API_KEY")
    eleven_labs_model: Optional[str] = os.environ.get("ELEVENLABS_MODEL", "eleven_v3")
    if not api_key:
        return None
    voice_id: str = "VMEiS9pN5WcJdwYFOr4i"
    url: str = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload: dict[str, Any] = {"text": spoken_text, "model_id": eleven_labs_model}
    headers: dict[str, str] = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except Exception as exc:
        logger.exception(f"ElevenLabs error: {exc}")
        return None
    filename: Path = Path(f"{secrets.token_hex(6)}.mp3")
    filename.write_bytes(response.content)
    return filename


def _choose_loop_video_for_emotion(emotion: str) -> Optional[Path]:
    static_dir: Path = Path().joinpath("static")
    pattern: str = f"officer_{emotion}*.mp4"
    matches: list[Path] = list(static_dir.glob(pattern))
    logger.info(f"Choosing loop video for emotion '{emotion}'. Found {len(matches)} matches.")
    if not matches:
        logger.info("No matching emotion video found, defaulting to neutral.")
        matches = list(static_dir.glob("officer_neutral.mp4"))
    if not matches:
        return None
    return secrets.choice(matches)


def _get_officer_reply_and_audio(
    user_text: str, history: list[dict[str, str]]
) -> tuple[str, str, Optional[str]]:
    """
    Get the officer's LLM reply and corresponding generated audio, without streaming.

    :param user_text: Latest user message
    :param history: Chat history (list of message dicts)
    :return: Tuple of (reply text, emotion label, base64 audio string or None)
    """
    system_preamble: str = (
        "You are a seasoned police officer conducting a formal interrogation. "
        "You are questioning a suspect about breaking into the Louvre and stealing some crowns ans jewels. "
        "Your tone is mostly calm, professional, and precise. "
        "Keep answers under 20 words. "
        "Ask pointed follow-up questions about times, methods, and accomplices. "
        "Make sure the text includes fitting tags like [angry], [sad], [coughs], [giggles], etc, or sound effects like [shot]. "
        "There is room for some humor in this. The officer can be sarcastic at times. And maybe he's even bribable."
        "Respond strictly as JSON: {\"text\": \"...\", \"emotion\": \"angry|cynical|happy|neutral|sad|surprised|suspicious\"}."
    )

    messages_for_llm = [
        {"role": "system", "content": system_preamble},
        *history,
        {"role": "user", "content": user_text},
    ]

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    try:
        response = client.chat.completions.create(
            model=os.environ.get("MODEL_NAME", "gpt-4.1-nano"),
            messages=messages_for_llm,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        logger.info(f"Assistant raw output: {content}")
    except Exception as exc:
        logger.exception(f"LLM request failed: {exc}")
        return "", "neutral", None

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.exception(f"Invalid JSON from model: {content}")
        return "", "neutral", None

    text: str = data.get("text", "")
    emotion: str = data.get("emotion", "neutral")

    audio_path = _generate_officer_audio(text)
    audio_b64 = _get_base64_audio(audio_path) if audio_path else None

    return text, emotion, audio_b64


def main() -> None:
    """
    Main entry point for the interrogation chat app.
    """
    st.set_page_config(page_title="Interrogation Chat", page_icon="🕵️", layout="wide")
    st.markdown(
        """
        <style>
        :root {
            --stage-h: 420px;         /* video stage height */
            --chat-input-h: 140px;    /* space reserved for chat input */
        }

        html, body {
            height: 100%;
            overflow: hidden;         /* disable page scroll */
            background-color: black;
        }

        .block-container {
            padding-top: var(--stage-h) !important;                 /* room under fixed video */
            padding-bottom: calc(var(--chat-input-h) + 20px) !important;
            background-color: black;
        }

        /* Pin the components iframe (video stage) to the top */
        iframe[title="st.iframe"] {
            position: fixed !important;
            top: 0; left: 0;
            width: 100vw !important;
            height: var(--stage-h) !important;
            z-index: 9998;
            border: none;
            pointer-events: auto;
            background: black;
        }

        /* Pin the chat input to the bottom */
        [data-testid="stChatInput"] {
            position: fixed;
            left: 0; right: 0;
            bottom: 0;
            height: var(--chat-input-h);
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

        /* Remove Streamlit's default grey focus overlay */
        [data-testid="stChatInput"] div:has(textarea:focus),
        [data-testid="stChatInput"] div:hover {
            background-color: transparent !important;
            box-shadow: none !important;
        }

        /* Only the chat history scrolls */
        [data-testid="stChatMessageList"] {
            position: fixed !important;
            top: calc(var(--stage-h) + 8px);
            left: 0; right: 0;
            bottom: calc(var(--chat-input-h) + 8px);
            overflow-y: auto !important;
            padding: 0 1rem;
        }

        footer, [data-testid="stStatusWidget"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _ensure_session()

    default_loop_path = Path().joinpath("static", "officer_loop.mp4")
    bg_audio_path = Path().joinpath("static", "tension.mp3")

    if not default_loop_path.exists():
        st.error("Video file not found (expected 'static/officer_loop.mp4').")
        return

    default_loop_src = _get_base64_video(default_loop_path)
    bg_audio_src = _get_base64_audio(bg_audio_path) if bg_audio_path.exists() else None
    emotion_loop_src = st.session_state.emotion_loop_b64
    speech_audio_src = st.session_state.speech_audio_b64

    user_input = st.chat_input("Type your message...")
    if user_input:
        _append_user_message(user_input)
        st.session_state.pending_user_input = user_input

    _render_scene(default_loop_src, emotion_loop_src, bg_audio_src, speech_audio_src)
    _render_history()

    # Auto-scroll chat history to bottom
    st.markdown(
        """
        <script>
        setTimeout(() => {
          const chatList = parent.document.querySelector('[data-testid="stChatMessageList"]');
          if (chatList) {
            chatList.scrollTop = chatList.scrollHeight;
          }
        }, 100);
        </script>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.pending_user_input:
        user_text = st.session_state.pending_user_input
        with st.chat_message("assistant"):
            reply, emotion, speech_b64 = _get_officer_reply_and_audio(
                user_text, st.session_state.messages[:-1]
            )
            st.markdown(reply)
        _append_assistant_message(reply)
        st.session_state.speech_audio_b64 = speech_b64
        path = _choose_loop_video_for_emotion(emotion)
        if path:
            st.session_state.emotion_loop_b64 = _get_base64_video(path)
        st.session_state.pending_user_input = None
        st.rerun()


if __name__ == "__main__":
    main()
