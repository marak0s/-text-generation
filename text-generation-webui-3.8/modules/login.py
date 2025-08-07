import json
from pathlib import Path
import yaml
import gradio as gr

from modules import shared, ui

_users = {}
# Map Gradio session hashes to logged-in usernames so multiple users can
# interact with the server without clobbering each other's state. When
# available, session information is also persisted in Apache Ignite so
# that logins survive application restarts and do not leak between users.
_session_users: dict[str, str] = {}

try:  # pragma: no cover - optional dependency and runtime service
    from pyignite import Client

    _ignite_client = Client()
    _ignite_client.connect("127.0.0.1", 10800)
    _session_cache = _ignite_client.get_or_create_cache("session_cache")
except Exception:  # pragma: no cover - fallback to in-process sessions
    _ignite_client = None
    _session_cache = None


def get_session_user(request: gr.Request | None = None) -> str:
    """Return the username associated with the current Gradio session."""
    if request is not None:
        try:
            # Prefer user information stored in the browser cookies so that
            # sessions survive page reloads and different session hashes.
            if hasattr(request, "cookies"):
                cookie_user = request.cookies.get("user")
                if cookie_user:
                    return cookie_user
        except Exception:
            # Fall back to the in-memory/session based mapping
            pass
        user = load_session_data(request.session_hash)
        return user or "anonymous"
    return "anonymous"

def save_session_data(session_id: str, data: str) -> None:
    """Persist ``data`` for ``session_id`` in Ignite or fallback store."""
    if _session_cache is not None:
        try:
            _session_cache.put(session_id, data)
            return
        except Exception:
            pass
    _session_users[session_id] = data

def load_session_data(session_id: str) -> str | None:
    """Load data previously stored for ``session_id``."""
    if _session_cache is not None:
        try:
            return _session_cache.get(session_id)
        except Exception:
            return None
    return _session_users.get(session_id)


def get_user_settings_path(
    user: str | None = None, request: gr.Request | None = None
) -> Path:
    """Return the settings.yaml path for the given user or session."""
    user = user or get_session_user(request)
    return Path(f'user_data/sessions/{user}/settings.yaml')


def load_user_settings(user: str) -> None:
    """Load settings for the given user and apply to the interface."""
    settings_path = get_user_settings_path(user)
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                new_settings = yaml.safe_load(f.read()) or {}
            shared.settings.update(new_settings)
            ui_updates = ui.apply_interface_values(new_settings)
            for name, update in zip(ui.list_interface_input_elements(), ui_updates):
                if name in shared.gradio:
                    shared.gradio[name].update(update)
        except Exception:
            pass


def load_users():
    global _users
    users_file = Path('user_data/users.json')
    if users_file.exists():
        with open(users_file, 'r', encoding='utf-8') as f:
            _users = json.load(f)
    else:
        _users = {}
    return _users


def verify_user(username: str, password: str) -> bool:
    users = load_users()
    return users.get(username) == password


def create_login_ui(login_block, interface_block):
    with login_block:
        username = gr.Textbox(label='Username')
        password = gr.Textbox(label='Password', type='password')
        login_btn = gr.Button('Login')
        msg = gr.HTML()
        success = gr.State(False)
        cookie = gr.State()

        def do_login(u, p, request: gr.Request):
            if verify_user(u, p):
                save_session_data(request.session_hash, u)
                load_user_settings(u)
                return (
                    gr.update(visible=False),
                    gr.update(visible=True),
                    '',
                    True,
                    gr.set_cookie('user', u),
                )
            return (
                gr.update(),
                gr.update(),
                '<span style="color:red">Invalid credentials</span>',
                False,
                None,
            )

        (
            login_btn.click(
                do_login,
                [username, password],
                [login_block, interface_block, msg, success, cookie],
            ).then(
                None,
                success,
                None,
                js='(s) => {window.dispatchEvent(new Event("resize")); if (s) window.location.reload();}',
            )
        )
    return

