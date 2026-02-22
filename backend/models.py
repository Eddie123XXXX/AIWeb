"""
数据模型定义
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from enum import Enum


class BaseSchema(BaseModel):
    """统一基础模型，关闭受保护命名空间限制"""
    model_config = ConfigDict(protected_namespaces=())


class Role(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseSchema):
    """单条消息"""
    role: Role
    content: str


class ChatRequest(BaseSchema):
    """聊天请求"""
    model_id: str = Field(..., description="使用的模型配置ID")
    messages: List[Message] = Field(..., description="对话历史")
    stream: bool = Field(default=True, description="是否流式返回")
    conversation_id: Optional[str] = Field(default=None, description="关联的会话ID，用于历史记录")
    temperature: Optional[float] = Field(default=None, description="温度参数，覆盖模型默认值")
    max_tokens: Optional[int] = Field(default=None, description="最大token数，覆盖模型默认值")


class ChatResponse(BaseSchema):
    """非流式聊天响应"""
    content: str
    model: str
    conversation_id: Optional[str] = Field(default=None, description="关联的会话ID（与请求一致）")
    usage: Optional[dict] = None


class ModelConfigCreate(BaseSchema):
    """创建模型配置的请求"""
    id: str = Field(..., description="配置唯一标识")
    name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="提供商: openai, anthropic, deepseek, qwen, moonshot, zhipu, custom")
    model_name: str = Field(..., description="实际模型名称")
    api_key: str = Field(..., description="API密钥")
    api_base: Optional[str] = Field(default=None, description="自定义API地址(custom提供商必填)")
    max_tokens: int = Field(default=4096, description="最大token数")
    temperature: float = Field(default=0.7, description="默认温度")


class ModelConfigResponse(BaseSchema):
    """模型配置响应（隐藏API Key）"""
    id: str
    name: str
    display_name: Optional[str] = None  # 前端仅展示此名称，如 OpenAI、Claude、DeepSeek
    provider: str
    model_name: str
    api_base: Optional[str]
    max_tokens: int
    temperature: float
    api_key_preview: str  # 只显示部分 key


class ConversationInfo(BaseSchema):
    """对话信息（列表项）"""
    id: str
    title: str
    model_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationCreate(BaseSchema):
    """创建会话请求"""
    title: str = Field(default="新对话", description="会话标题")
    model_id: Optional[str] = Field(default=None, description="默认模型ID")


class ConversationUpdate(BaseSchema):
    """更新会话请求"""
    title: Optional[str] = Field(default=None, description="新标题")


class ConversationDetailResponse(BaseSchema):
    """会话详情（含消息列表）"""
    id: str
    title: str
    model_id: str
    created_at: datetime
    updated_at: datetime
    messages: List[Message] = Field(default_factory=list, description="消息列表")


class UserStatus(int, Enum):
    """用户状态（与 users 表 status 一致）"""
    DISABLED = 0   # 禁用
    NORMAL = 1     # 正常
    INACTIVE = 2   # 未激活
    LOCKED = 3     # 锁定


class UserProfile(BaseSchema):
    """用户资料（与 users 表对应，不含 password_hash）"""
    id: int = Field(..., description="主键ID")
    email: str = Field(..., description="登录邮箱")
    username: Optional[str] = Field(default=None, description="用户名/昵称")
    phone_code: Optional[str] = Field(default=None, description="国际区号")
    phone_number: Optional[str] = Field(default=None, description="手机号码")
    status: int = Field(default=1, description="状态: 0=禁用, 1=正常, 2=未激活, 3=锁定")
    last_login_ip: Optional[str] = Field(default=None, description="最后登录IP")
    last_login_at: Optional[datetime] = Field(default=None, description="最后登录时间")
    created_at: datetime = Field(..., description="注册时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class UserCreate(BaseSchema):
    """注册请求"""
    email: str = Field(..., description="登录邮箱")
    password: str = Field(..., min_length=6, description="密码（至少6位，存储时哈希）")
    username: Optional[str] = Field(default=None, max_length=64, description="用户名/昵称")
    phone_code: Optional[str] = Field(default=None, max_length=10, description="国际区号，如 +86")
    phone_number: Optional[str] = Field(default=None, max_length=20, description="手机号码")


class LoginRequest(BaseSchema):
    """登录请求"""
    email: str = Field(..., description="登录邮箱")
    password: str = Field(..., description="密码")


class TokenResponse(BaseSchema):
    """JWT 登录响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="类型")
    expires_in: int = Field(..., description="过期秒数")


class LoginUserInfo(BaseSchema):
    """登录返回的用户基本信息（users + user_profiles 昵称/头像）"""
    id: int = Field(..., description="用户ID")
    email: str = Field(..., description="邮箱")
    username: Optional[str] = Field(default=None, description="用户名")
    nickname: Optional[str] = Field(default=None, description="昵称（来自 user_profiles）")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL（来自 user_profiles）")


class LoginResponse(BaseSchema):
    """登录成功响应：JWT + 用户信息"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="类型")
    expires_in: int = Field(..., description="过期秒数")
    user: LoginUserInfo = Field(..., description="当前用户基本信息")


# ---------- user_oauths 表（第三方登录）----------

class OAuthLoginRequest(BaseSchema):
    """第三方登录/注册请求（前端拿到 provider 返回的 uid 等信息后调用）"""
    provider: str = Field(..., max_length=32, description="如 google, wechat, github, apple")
    provider_uid: str = Field(..., max_length=255, description="第三方唯一用户 ID")
    provider_data: Optional[dict] = Field(default=None, description="第三方返回的昵称、头像等冗余信息")


class OAuthBindRequest(BaseSchema):
    """绑定当前账号与第三方（需已登录）"""
    provider: str = Field(..., max_length=32)
    provider_uid: str = Field(..., max_length=255)
    provider_data: Optional[dict] = Field(default=None)


class OAuthRecordResponse(BaseSchema):
    """一条第三方绑定记录"""
    id: int
    user_id: int
    provider: str
    provider_uid: str
    provider_data: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseSchema):
    """更新 users 表字段请求"""
    username: Optional[str] = Field(default=None, max_length=64, description="用户名/昵称")
    phone_code: Optional[str] = Field(default=None, max_length=10, description="国际区号")
    phone_number: Optional[str] = Field(default=None, max_length=20, description="手机号码")


# ---------- user_profiles 表（资料扩展）----------

class ProfileGender(int, Enum):
    """性别（与 user_profiles.gender 一致）"""
    UNKNOWN = 0   # 保密/未知
    MALE = 1      # 男
    FEMALE = 2    # 女
    OTHER = 9     # 其他


class ProfileData(BaseSchema):
    """用户资料扩展（user_profiles 表）"""
    user_id: int
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    gender: int = Field(default=0, description="0=保密, 1=男, 2=女, 9=其他")
    birthday: Optional[str] = None  # YYYY-MM-DD
    location: Optional[str] = None
    website: Optional[str] = None
    preferences: Optional[dict] = Field(default=None, description="主题、语言、默认模型等 JSON")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class ProfileUpdate(BaseSchema):
    """更新 user_profiles 请求（仅传要改的字段）"""
    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    bio: Optional[str] = Field(default=None, max_length=500)
    gender: Optional[int] = Field(default=None, description="0=保密, 1=男, 2=女, 9=其他")
    birthday: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    location: Optional[str] = Field(default=None, max_length=100)
    website: Optional[str] = Field(default=None, max_length=255)
    preferences: Optional[dict] = Field(default=None, description="用户偏好 JSON")


class UserProfileMe(BaseSchema):
    """GET /user/me 合并返回：users + user_profiles"""
    id: int
    email: str
    username: Optional[str] = None
    phone_code: Optional[str] = None
    phone_number: Optional[str] = None
    status: int = 1
    last_login_ip: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    profile: Optional[ProfileData] = Field(default=None, description="扩展资料，无则 null")
