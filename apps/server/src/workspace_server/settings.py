"""Configuration from the environment (and a `.env` file), with safe local defaults.

A Contxt folder (its "home") holds `brain/` (the Brain, its own git repository), `data/` (the
app's database, uploaded files, sign-in key and backups), `outputs/` (what the AI makes) and
`.env`. Relative paths in the settings are read from the home, so a home can move as a whole.
Every setting is `CONTXT_<NAME>`; the earlier `WORKSPACE_<NAME>` is still read.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field

from workspace_core.services.actors import TOKEN_PREFIX


def load_dotenv(path: str = ".env") -> None:
    """KEY=VALUE lines into os.environ, without overriding what is already set."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


PREFIXES = ("CONTXT_", "WORKSPACE_")  # WORKSPACE_ is the earlier name, still read
HOME_VAULT = ("brain", "vault", "brain.json")  # a home's Brain, found without being named


def setting(name: str) -> str | None:
    """`CONTXT_<name>`, else the earlier `WORKSPACE_<name>`; None when neither is set."""
    for prefix in PREFIXES:
        value = os.environ.get(prefix + name)
        if value is not None and value != "":
            return value
    return None


def _flag(name: str, default: bool) -> bool:
    value = setting(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    data_dir: str = "data"
    database_url: str | None = None
    brain_vault: str | None = None
    brain_embeddings: bool = True
    host: str = "127.0.0.1"
    port: int = 8787
    public_url: str | None = None
    owner_token: str | None = None
    name: str = "Contxt"
    timezone: str = "UTC"
    web_dist: str | None = None
    exports_dir: str | None = None
    lease_seconds: int = 900
    worker_interval: float = 15.0
    allowed_origins: list[str] = field(default_factory=list)
    trust_proxy: bool = False
    speech_models_dir: str | None = None

    @classmethod
    def from_env(cls, env_file: str | None = ".env", *, home: str | None = None) -> Settings:
        """The settings of one home: `home/.env` (or `env_file`) and the environment. Relative
        paths count from the home, else from the env file's folder, else the current one. A
        home (named, or the folder of a settings file that exists) has its `brain/vault` and
        `outputs/` found without being named; the current folder alone never does."""
        if home and env_file in (None, ".env"):
            env_file = os.path.join(home, ".env")
        if env_file:
            load_dotenv(env_file)
        if home:
            base, is_home = os.path.abspath(home), True
        elif env_file and os.path.isfile(env_file):
            base, is_home = os.path.dirname(os.path.abspath(env_file)), True
        else:
            base, is_home = os.getcwd(), False

        def place(value: str | None) -> str | None:
            if not value:
                return None
            value = os.path.expanduser(value)
            return value if os.path.isabs(value) else os.path.normpath(os.path.join(base, value))

        brain_vault = setting("BRAIN_VAULT")
        if not brain_vault and is_home and os.path.isfile(os.path.join(base, *HOME_VAULT)):
            brain_vault = os.path.join("brain", "vault")
        exports_dir = setting("EXPORTS_DIR")
        if not exports_dir and is_home and os.path.isdir(os.path.join(base, "outputs")):
            exports_dir = "outputs"
        return cls(
            data_dir=place(setting("DATA_DIR") or "data") or "data",
            database_url=setting("DATABASE_URL"),
            brain_vault=place(brain_vault),
            brain_embeddings=_flag("BRAIN_EMBEDDINGS", True),
            host=setting("HOST") or "127.0.0.1",
            port=int(setting("PORT") or 8787),
            public_url=setting("PUBLIC_URL"),
            owner_token=setting("OWNER_TOKEN"),
            name=setting("NAME") or "Contxt",
            timezone=setting("TIMEZONE") or "UTC",
            web_dist=place(setting("WEB_DIST")),
            exports_dir=place(exports_dir),
            lease_seconds=int(setting("LEASE_SECONDS") or 900),
            worker_interval=float(setting("WORKER_INTERVAL") or 15),
            trust_proxy=_flag("TRUST_PROXY", False),
            speech_models_dir=place(setting("SPEECH_MODELS")),
            allowed_origins=[
                o.strip() for o in (setting("ALLOWED_ORIGINS") or "").split(",") if o.strip()
            ],
        )

    @property
    def base_url(self) -> str:
        if self.public_url:
            return self.public_url.rstrip("/")
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}"

    @property
    def secrets_dir(self) -> str:
        return os.path.join(self.data_dir, "secrets")

    @property
    def speech_models(self) -> str:
        """Where the speech model lives: beside the Brain's embedding model, or in the data
        folder when no Brain is connected."""
        if self.speech_models_dir:
            return self.speech_models_dir
        if self.brain_vault:
            return os.path.join(self.brain_vault, ".brain", "models")
        return os.path.join(self.data_dir, "models")

    def resolved_owner_token(self) -> str:
        """The owner token: from the environment, or generated once into the data folder."""
        if self.owner_token:
            return self.owner_token
        path = os.path.join(self.secrets_dir, "owner-token")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        os.makedirs(self.secrets_dir, exist_ok=True)
        token = new_token()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return token


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)
