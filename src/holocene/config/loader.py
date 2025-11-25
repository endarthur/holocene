"""Configuration loading and management."""

import os
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PrivacyConfig(BaseModel):
    """Privacy settings."""

    tier: str = "external_api"  # external_api, local_only
    blacklist_domains: List[str] = Field(default_factory=list)
    blacklist_keywords: List[str] = Field(default_factory=list)
    blacklist_paths: List[str] = Field(default_factory=list)
    whitelist_domains: List[str] = Field(default_factory=list)


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "nanogpt"
    api_key: Optional[str] = None
    base_url: str = "https://nano-gpt.com/api/v1"
    daily_budget: int = 2000

    # Model routing
    primary: str = "deepseek-ai/DeepSeek-V3.1"
    primary_cheap: str = "deepseek-chat-cheaper"
    coding: str = "qwen/qwen3-coder"
    reasoning: str = "deepseek-r1"
    reasoning_cheap: str = "deepseek-reasoner-cheaper"
    verification: str = "nousresearch/hermes-4-70b"
    verification_alt: str = "z-ai/glm-4.6"
    lightweight: str = "meta-llama/llama-3.2-3b-instruct"
    canary: str = "mistralai/mistral-tiny"
    vision: str = "qwen25-vl-72b-instruct"
    vision_powerful: str = "meta-llama/llama-3.2-90b-vision-instruct"


class ClassificationConfig(BaseModel):
    """Library classification system configuration."""

    system: str = "Dewey"  # Dewey, UDC, or LCC
    generate_cutter_numbers: bool = True  # Generate Cutter numbers for unique shelf positions
    generate_full_call_numbers: bool = True  # Generate complete call numbers (e.g., "550.182 I73a")
    cutter_length: int = 3  # Number of characters in Cutter number (typically 2-4)


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""

    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[int] = None  # Telegram chat ID for notifications


class MercadoLivreConfig(BaseModel):
    """Mercado Livre integration configuration."""

    enabled: bool = False
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: str = "https://127.0.0.1:8080/auth/callback"

    # OAuth tokens (managed automatically)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[str] = None

    # Sync settings
    auto_sync: bool = False
    sync_interval_hours: int = 24

    # Classification
    auto_classify: bool = True
    classify_as_web: bool = True  # Use W prefix for Extended Dewey

    # HTML caching (for paid proxy services)
    cache_html: bool = True  # Cache fetched HTML to avoid re-fetching costs


class IntegrationsConfig(BaseModel):
    """Integration settings for external services."""

    journel_enabled: bool = False
    journel_path: Optional[Path] = None
    journel_ignore_projects: List[str] = Field(default_factory=list)

    github_enabled: bool = False
    github_token: Optional[str] = None
    github_scan_path: Optional[Path] = None

    internet_archive_enabled: bool = False
    ia_access_key: Optional[str] = None
    ia_secret_key: Optional[str] = None
    ia_rate_limit_seconds: float = 2.0  # Conservative: 2x IA's 1 req/sec recommendation

    calibre_enabled: bool = False
    calibre_library_path: Optional[Path] = None
    calibre_auto_add_ia_books: bool = True  # Auto-add IA books to Calibre when downloading
    calibre_content_server_port: int = 8080  # Port for Calibre Content server
    calibre_username: Optional[str] = None  # Username for Content server (optional)
    calibre_password: Optional[str] = None  # Password for Content server (optional)

    apify_enabled: bool = False
    apify_api_key: Optional[str] = None

    brightdata_enabled: bool = False
    brightdata_username: Optional[str] = None
    brightdata_password: Optional[str] = None
    brightdata_host: str = "brd.superproxy.io"
    brightdata_port: int = 22225

    browser_enabled: bool = False
    browser_sampling_interval: int = 30  # seconds

    window_focus_enabled: bool = False
    window_sampling_interval: int = 30

    # ArchiveBox integration
    archivebox_enabled: bool = False
    archivebox_host: str = "192.168.1.102"
    archivebox_user: str = "holocene"
    archivebox_data_dir: str = "/opt/archivebox/data"

    # Proxmox API (for monitoring and limited control)
    proxmox_enabled: bool = False
    proxmox_host: str = "192.168.1.101"
    proxmox_port: int = 8006
    proxmox_api_token_id: Optional[str] = None  # Format: "user@realm!tokenid"
    proxmox_api_token_secret: Optional[str] = None
    proxmox_verify_ssl: bool = False  # Set to True if using valid SSL cert

    # Uptime Kuma (monitoring dashboard)
    uptime_kuma_enabled: bool = False
    uptime_kuma_url: str = "http://192.168.1.103:3001"
    uptime_kuma_api_key: Optional[str] = None
    uptime_kuma_push_token: Optional[str] = None  # For push monitor (daemon pings Uptime Kuma)

    def model_post_init(self, __context):
        """Expand paths after initialization."""
        if self.journel_path:
            self.journel_path = Path(self.journel_path).expanduser()
        if self.github_scan_path:
            self.github_scan_path = Path(self.github_scan_path).expanduser()
        if self.calibre_library_path:
            self.calibre_library_path = Path(self.calibre_library_path).expanduser()


class Config(BaseModel):
    """Main Holocene configuration."""

    # Storage paths
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".holocene")
    db_path: Optional[Path] = None  # Will default to data_dir / holocene.db

    # Monitoring
    healthcheck_url: Optional[str] = None  # healthchecks.io ping URL (e.g., https://hc-ping.com/your-uuid)

    # Sub-configs
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    mercadolivre: MercadoLivreConfig = Field(default_factory=MercadoLivreConfig)

    def model_post_init(self, __context):
        """Post-initialization hook to set defaults."""
        # Ensure data_dir exists
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set db_path if not specified
        if self.db_path is None:
            self.db_path = self.data_dir / "holocene.db"
        else:
            self.db_path = Path(self.db_path)

        # Load API keys from env if not in config
        if self.llm.api_key is None:
            self.llm.api_key = os.getenv("NANOGPT_API_KEY")

        if self.integrations.apify_api_key is None:
            self.integrations.apify_api_key = os.getenv("APIFY_API_KEY")


def get_config_path() -> Path:
    """Get the path to the config file."""
    return Path.home() / ".config" / "holocene" / "config.yml"


DEFAULT_CONFIG = """# Holocene Configuration

# Monitoring (optional)
# healthcheck_url: "https://hc-ping.com/your-uuid-here"  # healthchecks.io ping URL

privacy:
  tier: external_api  # external_api or local_only

  blacklist_domains:
    - "*.vale.com"
    - "mail.google.com"

  blacklist_keywords: []
    # Add sensitive keywords here
    # - "confidential"

  blacklist_paths: []
    # Add sensitive paths here
    # - "/work/proprietary"

  whitelist_domains:
    - "github.com"
    - "*.wikipedia.org"

llm:
  provider: nanogpt
  # api_key: set via NANOGPT_API_KEY env var or paste here
  base_url: https://nano-gpt.com/api/v1
  daily_budget: 2000

  # Model routing (NanoGPT model IDs)
  primary: deepseek-ai/DeepSeek-V3.1
  primary_cheap: deepseek-chat-cheaper
  coding: qwen/qwen3-coder
  reasoning: deepseek-r1
  verification: nousresearch/hermes-4-70b

classification:
  # Library classification system for organizing your collection
  system: Dewey  # Dewey (default), UDC, or LCC
  generate_cutter_numbers: true  # Add Cutter numbers for unique shelf positions
  generate_full_call_numbers: true  # Generate complete call numbers (e.g., "550.182 I73a")
  cutter_length: 3  # Characters in Cutter number (2-4, typically 3)

integrations:
  journel_enabled: false
  # journel_path: ~/journel
  journel_ignore_projects: []

  calibre_enabled: false
  # calibre_library_path: ~/Calibre Library
  calibre_auto_add_ia_books: true  # Auto-add Internet Archive books to Calibre

  browser_enabled: false
  browser_sampling_interval: 30

  window_focus_enabled: false
  window_sampling_interval: 30

telegram:
  enabled: false
  # bot_token: "YOUR_BOT_TOKEN"  # Get from @BotFather on Telegram
  # chat_id: 123456789  # Your Telegram user ID (get from @userinfobot)

mercadolivre:
  enabled: false
  # client_id: "YOUR_CLIENT_ID"
  # client_secret: "YOUR_CLIENT_SECRET"
  redirect_uri: "https://127.0.0.1:8080/auth/callback"

  # OAuth tokens (managed automatically - don't edit manually)
  # access_token: null
  # refresh_token: null
  # token_expires_at: null

  # Sync settings
  auto_sync: false
  sync_interval_hours: 24

  # Classification
  auto_classify: true  # Automatically classify with Extended Dewey
  classify_as_web: true  # Use W prefix for web content

  # HTML caching (recommended when using paid proxy services)
  cache_html: true  # Save fetched HTML to avoid re-fetch costs

  # Proxmox API (for monitoring containers/VMs)
  proxmox_enabled: false
  proxmox_host: "192.168.1.101"  # Your Proxmox host IP
  proxmox_port: 8006
  # proxmox_api_token_id: "claude-assistant@pve!readonly"
  # proxmox_api_token_secret: "your-secret-here"
  proxmox_verify_ssl: false  # Set to true if using valid SSL cert

  # Uptime Kuma (monitoring dashboard)
  uptime_kuma_enabled: false
  uptime_kuma_url: "http://192.168.1.103:3001"
  # uptime_kuma_api_key: "uk_xxxxx"  # Generate in Uptime Kuma Settings → API Keys
  # uptime_kuma_push_token: "abc123"  # Create Push monitor, copy token from URL
"""


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from file or create default."""
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        # Return default config
        return Config()

    # Load from YAML
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    return Config(**data)


def save_config(config: Config, config_path: Optional[Path] = None):
    """Save configuration to file."""
    if config_path is None:
        config_path = get_config_path()

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict and save as YAML
    data = config.model_dump(mode="json", exclude={"data_dir", "db_path"})

    # Convert paths to strings
    if "journel_path" in data.get("integrations", {}):
        jp = data["integrations"]["journel_path"]
        if jp:
            data["integrations"]["journel_path"] = str(jp)

    if "calibre_library_path" in data.get("integrations", {}):
        clp = data["integrations"]["calibre_library_path"]
        if clp:
            data["integrations"]["calibre_library_path"] = str(clp)

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
