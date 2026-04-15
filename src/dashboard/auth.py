"""
Módulo de autenticação para o Dashboard de Crédito.

Gerencia login, registro de novos usuários e painel de aprovação admin.

Backend:
  - Streamlit Cloud (deploy): Google Sheets via gspread (persistente)
  - Localhost: YAML local (fallback)
"""

import os
import yaml
import bcrypt
import streamlit as st
from datetime import datetime

# Caminhos dos arquivos YAML (fallback local)
AUTH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
USERS_FILE = os.path.join(AUTH_DIR, "users.yaml")
PENDING_FILE = os.path.join(AUTH_DIR, "pending_users.yaml")


# =========================================================================
# Backend: Google Sheets
# =========================================================================

def _use_gsheets() -> bool:
    """Retorna True se deve usar Google Sheets (credenciais disponíveis)."""
    try:
        secrets = st.secrets
        return "gcp_service_account" in secrets and "gsheets" in secrets
    except Exception:
        return False


def _get_gsheets_client():
    """Retorna cliente gspread autenticado via service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds)


@st.cache_resource(ttl=60)
def _get_spreadsheet():
    """Retorna a planilha (cacheada por 60s)."""
    client = _get_gsheets_client()
    sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
    return client.open_by_url(sheet_url)


def _get_worksheet(name: str):
    """Retorna (ou cria) uma aba da planilha."""
    spreadsheet = _get_spreadsheet()
    try:
        return spreadsheet.worksheet(name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=name, rows=100, cols=10)
        if name == "users":
            ws.append_row(["username", "name", "email", "password", "role", "approved"])
        elif name == "pending":
            ws.append_row(["username", "name", "email", "password", "requested_at"])
        return ws


def _gsheets_load_users() -> dict:
    """Carrega usuários do Google Sheets."""
    ws = _get_worksheet("users")
    records = ws.get_all_records()
    users = {}
    for row in records:
        if row.get("username"):
            users[row["username"]] = {
                "name": row.get("name", ""),
                "email": row.get("email", ""),
                "password": row.get("password", ""),
                "role": row.get("role", "viewer"),
                "approved": str(row.get("approved", "")).lower() in ("true", "1", "yes"),
            }
    return users


def _gsheets_save_user(username: str, user_data: dict):
    """Salva/atualiza um usuário no Google Sheets."""
    ws = _get_worksheet("users")
    records = ws.get_all_records()

    # Verificar se já existe
    for idx, row in enumerate(records):
        if row.get("username") == username:
            # Atualizar (row index = idx + 2: +1 header, +1 zero-based)
            row_num = idx + 2
            ws.update(f"A{row_num}:F{row_num}", [[
                username,
                user_data.get("name", ""),
                user_data.get("email", ""),
                user_data.get("password", ""),
                user_data.get("role", "viewer"),
                str(user_data.get("approved", False)),
            ]])
            return

    # Novo usuário
    ws.append_row([
        username,
        user_data.get("name", ""),
        user_data.get("email", ""),
        user_data.get("password", ""),
        user_data.get("role", "viewer"),
        str(user_data.get("approved", False)),
    ])


def _gsheets_load_pending() -> list:
    """Carrega solicitações pendentes do Google Sheets."""
    ws = _get_worksheet("pending")
    records = ws.get_all_records()
    return [r for r in records if r.get("username")]


def _gsheets_add_pending(pending: dict):
    """Adiciona solicitação pendente."""
    ws = _get_worksheet("pending")
    ws.append_row([
        pending.get("username", ""),
        pending.get("name", ""),
        pending.get("email", ""),
        pending.get("password", ""),
        pending.get("requested_at", ""),
    ])


def _gsheets_remove_pending(username: str):
    """Remove solicitação pendente pelo username."""
    ws = _get_worksheet("pending")
    records = ws.get_all_records()
    for idx, row in enumerate(records):
        if row.get("username") == username:
            ws.delete_rows(idx + 2)  # +1 header, +1 zero-based
            return


# =========================================================================
# Backend: YAML (fallback local)
# =========================================================================

def _load_yaml(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# =========================================================================
# Interface unificada
# =========================================================================

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def _load_users() -> dict:
    """Carrega usuários (Google Sheets ou YAML). Fallback para YAML se GSheets falhar."""
    if _use_gsheets():
        try:
            return _gsheets_load_users()
        except Exception as e:
            # Fallback offline: se não conseguir acessar Google Sheets, usar YAML local
            import streamlit as st
            st.warning(f"⚠️ Modo offline: usando usuários locais (Google Sheets inacessível: {str(e)[:80]})", icon="🔌")
            _ensure_users_file()
            data = _load_yaml(USERS_FILE)
            return data.get("users", {})

    _ensure_users_file()
    data = _load_yaml(USERS_FILE)
    return data.get("users", {})


def _save_user(username: str, user_data: dict):
    """Salva um usuário (Google Sheets ou YAML). Fallback para YAML se GSheets falhar."""
    if _use_gsheets():
        try:
            _gsheets_save_user(username, user_data)
            _get_spreadsheet.clear()  # Limpar cache
            return
        except Exception:
            pass  # Fallback para YAML

    _ensure_users_file()
    data = _load_yaml(USERS_FILE)
    data.setdefault("users", {})[username] = user_data
    _save_yaml(USERS_FILE, data)


def _load_pending() -> list:
    """Carrega pendentes (Google Sheets ou YAML). Fallback para YAML se GSheets falhar."""
    if _use_gsheets():
        try:
            return _gsheets_load_pending()
        except Exception:
            pass  # Fallback silencioso (warning já foi exibido em _load_users)

    _ensure_pending_file()
    data = _load_yaml(PENDING_FILE)
    return data.get("pending", [])


def _add_pending(pending: dict):
    """Adiciona pendente (Google Sheets ou YAML)."""
    if _use_gsheets():
        try:
            _gsheets_add_pending(pending)
            _get_spreadsheet.clear()
            return
        except Exception:
            pass  # Fallback para YAML

    _ensure_pending_file()
    data = _load_yaml(PENDING_FILE)
    data.setdefault("pending", []).append(pending)
    _save_yaml(PENDING_FILE, data)


def _remove_pending(username: str):
    """Remove pendente (Google Sheets ou YAML)."""
    if _use_gsheets():
        try:
            _gsheets_remove_pending(username)
            _get_spreadsheet.clear()
            return
        except Exception:
            pass  # Fallback para YAML

    _ensure_pending_file()
    data = _load_yaml(PENDING_FILE)
    data["pending"] = [p for p in data.get("pending", []) if p["username"] != username]
    _save_yaml(PENDING_FILE, data)


def _ensure_users_file():
    """Cria o arquivo de usuários com o admin padrão se não existir."""
    if not os.path.exists(USERS_FILE):
        admin_data = {
            "users": {
                "admin": {
                    "name": "Administrador",
                    "email": "admin@dashboard.com",
                    "password": _hash_password("admin123"),
                    "role": "admin",
                    "approved": True,
                }
            },
        }
        _save_yaml(USERS_FILE, admin_data)


def _ensure_pending_file():
    if not os.path.exists(PENDING_FILE):
        _save_yaml(PENDING_FILE, {"pending": []})


# =========================================================================
# UI Components
# =========================================================================

def show_login() -> tuple[bool, str, str]:
    """Exibe formulário de login. Returns: (authenticated, username, role)"""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["username"] = ""
        st.session_state["user_role"] = ""

    if st.session_state["authenticated"]:
        return True, st.session_state["username"], st.session_state["user_role"]

    users = _load_users()

    st.markdown("### Login")
    username = st.text_input("Usuário", key="login_username")
    password = st.text_input("Senha", type="password", key="login_password")

    if st.button("Entrar", key="login_btn"):
        if username in users:
            user = users[username]
            if user.get("approved", False) and _check_password(password, user["password"]):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.session_state["user_role"] = user.get("role", "viewer")
                st.rerun()
            elif not user.get("approved", False):
                st.error("Sua conta ainda aguarda aprovação do administrador.")
            else:
                st.error("Usuário ou senha incorretos.")
        else:
            st.error("Usuário ou senha incorretos.")

    return False, "", ""


def show_registration_form():
    """Exibe formulário de registro (solicitação de conta)."""
    st.markdown("### Solicitar Acesso")
    st.info("Preencha o formulário abaixo. Sua solicitação será enviada ao administrador para aprovação.")

    with st.form("registration_form", clear_on_submit=True):
        name = st.text_input("Nome completo")
        email = st.text_input("Email")
        username = st.text_input("Nome de usuário (para login)")
        password = st.text_input("Senha", type="password")
        password_confirm = st.text_input("Confirmar senha", type="password")

        submitted = st.form_submit_button("Solicitar cadastro")

        if submitted:
            if not all([name, email, username, password, password_confirm]):
                st.error("Preencha todos os campos.")
                return

            if password != password_confirm:
                st.error("As senhas não coincidem.")
                return

            if len(password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
                return

            # Verificar se username já existe
            users = _load_users()
            if username in users:
                st.error("Este nome de usuário já está em uso.")
                return

            # Verificar se já tem solicitação pendente
            pending_list = _load_pending()
            if any(p["username"] == username for p in pending_list):
                st.warning("Já existe uma solicitação pendente com este nome de usuário.")
                return

            # Adicionar à lista de pendentes
            _add_pending({
                "username": username,
                "name": name,
                "email": email,
                "password": _hash_password(password),
                "requested_at": datetime.now().isoformat(),
            })
            st.success("Solicitação enviada! Aguarde a aprovação do administrador.")


def show_admin_panel():
    """Painel de aprovação de usuários (apenas para admin)."""
    pending_list = _load_pending()
    users = _load_users()

    with st.sidebar.expander(f"Admin — Usuários ({len(pending_list)} pendentes)", expanded=False):
        # Usuários aprovados
        st.markdown("**Usuários ativos:**")
        for uname, udata in users.items():
            role_badge = "admin" if udata.get("role") == "admin" else "viewer"
            st.markdown(f"- `{uname}` ({udata.get('name', '')}) — {role_badge}")

        st.markdown("---")

        # Solicitações pendentes
        if pending_list:
            st.markdown("**Solicitações pendentes:**")
            for idx, pending in enumerate(pending_list):
                st.markdown(
                    f"**{pending['name']}** (`{pending['username']}`)\n\n"
                    f"Email: {pending['email']}\n\n"
                    f"Solicitado em: {str(pending.get('requested_at', ''))[:10]}"
                )
                col_approve, col_reject = st.columns(2)
                with col_approve:
                    if st.button("Aprovar", key=f"approve_{idx}"):
                        _save_user(pending["username"], {
                            "name": pending["name"],
                            "email": pending["email"],
                            "password": pending["password"],
                            "role": "viewer",
                            "approved": True,
                        })
                        _remove_pending(pending["username"])
                        st.rerun()

                with col_reject:
                    if st.button("Rejeitar", key=f"reject_{idx}"):
                        _remove_pending(pending["username"])
                        st.rerun()

                st.markdown("---")
        else:
            st.caption("Nenhuma solicitação pendente.")


def show_logout():
    """Botão de logout na sidebar."""
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"Logado como: **{st.session_state.get('username', '')}**")
        if st.button("Sair", key="logout_btn"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.session_state["user_role"] = ""
            st.rerun()
