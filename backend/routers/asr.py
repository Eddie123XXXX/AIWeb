"""
语音识别路由：浏览器不支持 Web Speech API 时，前端录音上传，后端转 MP3 后调用 Qwen3-ASR-Flash 转写。
需配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY；非 MP3/WAV 格式需安装 ffmpeg（供 pydub 转码）。
"""
import base64
import io
import os
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/asr", tags=["asr"])

# 优先 DASHSCOPE_API_KEY（百炼），其次 QWEN_API_KEY（通义）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_API_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 10MB 限制（与 DashScope 一致）
MAX_AUDIO_BYTES = 10 * 1024 * 1024

# Qwen3-ASR-Flash 支持的格式，可直接使用；其余格式（如 webm）需转为 MP3
ASR_SUPPORTED_TYPES = ("audio/mpeg", "audio/mp3", "audio/wav", "audio/wave")


def _get_client():
    if not DASHSCOPE_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)


def _to_mp3_bytes(raw: bytes, content_type: str) -> bytes:
    """将 webm 等格式转为 MP3 字节（pydub 依赖 ffmpeg）。"""
    from pydub import AudioSegment

    # 根据 content_type 推断 pydub 格式名
    ct = (content_type or "").strip().lower()
    if "webm" in ct or "ogg" in ct:
        fmt = "webm"
    elif "mp4" in ct or "m4a" in ct:
        fmt = "mp4"
    elif "wav" in ct:
        fmt = "wav"
    elif "mp3" in ct or "mpeg" in ct:
        return raw  # 已是 MP3，无需转换
    else:
        fmt = "webm"  # 前端默认上传 webm
    buf = io.BytesIO(raw)
    segment = AudioSegment.from_file(buf, format=fmt)
    out = io.BytesIO()
    segment.export(out, format="mp3")
    return out.getvalue()


@router.post("/transcribe", summary="语音转文字（Qwen3-ASR-Flash）")
async def transcribe_audio(audio: UploadFile = File(..., description="录音文件（支持 webm，会转为 MP3 后识别）")):
    """
    接收前端上传的录音；若为 webm 等格式则先转为 MP3，再调用通义 qwen3-asr-flash 转写。
    当浏览器不支持 Web Speech API 时，前端用 MediaRecorder 录音后调用此接口。
    """
    client = _get_client()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="未配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY，无法使用云端语音识别",
        )

    content_type = (audio.content_type or "").strip().lower() or "audio/webm"
    if not content_type.startswith("audio/"):
        content_type = "audio/webm"

    body = await audio.read()
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"音频大小超过限制（最大 10MB），当前 {len(body) / (1024 * 1024):.2f}MB",
        )
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="音频为空")

    # 非 ASR 支持格式则转为 MP3
    if content_type not in ASR_SUPPORTED_TYPES:
        try:
            body = _to_mp3_bytes(body, content_type)
            content_type = "audio/mpeg"
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"音频转 MP3 失败（请确认已安装 ffmpeg）: {str(e)}",
            )

    b64 = base64.b64encode(body).decode("ascii")
    data_uri = f"data:{content_type};base64,{b64}"

    try:
        completion = client.chat.completions.create(
            model="qwen3-asr-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": data_uri},
                        }
                    ],
                }
            ],
            stream=False,
            extra_body={
                "asr_options": {
                    "enable_itn": False,
                }
            },
        )
        text = (completion.choices[0].message.content or "").strip()
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音识别失败: {str(e)}")
