"""
Dashboard Streamlit — Google Sheets Real-Time Monitor
Executa: streamlit run sheet_app.py
"""
import time
import json
import csv
import urllib.request
import urllib.parse
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone, timedelta

# ─── Configuração de Página ───────────────────────────────────
st.set_page_config(
    page_title="Google Sheets Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilos CSS Avançados (Dark Mode Premium) ───────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }

/* Dashboard Cards */
.status-card {
    background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
    border: 1px solid rgba(100, 255, 218, 0.15);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.status-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #64ffda, #00b0ff);
}
.card-header {
    font-size: 13px;
    font-weight: 700;
    color: #7f8fb0;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
}
.card-value {
    font-size: 36px;
    font-weight: 700;
    color: #f3f4f6;
}
.card-sub {
    font-size: 13px;
    color: #64ffda;
    margin-top: 6px;
}

/* Glowing Visual Alert Card */
.glow-alert-box {
    background: linear-gradient(135deg, #7b0000 0%, #c0392b 100%);
    border: 2px solid #ff6b6b;
    border-radius: 16px;
    padding: 20px 24px;
    color: #ffffff;
    font-weight: 600;
    font-size: 16px;
    margin-bottom: 25px;
    box-shadow: 0 0 20px rgba(231, 76, 60, 0.4);
    border-left: 6px solid #ff3b30;
    animation: glow-pulse 1.5s infinite alternate;
}
@keyframes glow-pulse {
    0% { box-shadow: 0 0 10px rgba(231, 76, 60, 0.3); }
    100% { box-shadow: 0 0 25px rgba(231, 76, 60, 0.6); }
}

/* Highlight Row styling */
.highlight-text {
    color: #64ffda !important;
    font-weight: bold !important;
}

/* Audit Logs */
.audit-row {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 12px 18px;
    margin-bottom: 8px;
    border-left: 4px solid #64ffda;
    color: #ccd6f6;
}

.status-indicator-dot {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
}
.dot-green { background-color: #64ffda; box-shadow: 0 0 8px #64ffda; }
.dot-orange { background-color: #f39c12; box-shadow: 0 0 8px #f39c12; }
.dot-red { background-color: #e74c3c; box-shadow: 0 0 8px #e74c3c; }

/* Custom Sidebar styling */
div[data-testid="stSidebar"] {
    background: #0b0f19;
    border-right: 1px solid rgba(255, 255, 255, 0.05);
}
</style>
""", unsafe_allow_html=True)

# ─── Caminhos dos Arquivos de Configuração ─────────────────────
CONFIG_FILE = Path(__file__).parent / "sheet_config.json"
STATE_FILE = Path(__file__).parent / "sheet_state.json"
AUDIT_LOG_FILE = Path(__file__).parent / "sheet_changes_log.json"

# ─── Funções de Hora (Fuso -3) ──────────────────────────────────
def get_local_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=-3)))

# ─── Gerenciamento de Configuração ─────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Configuração Padrão
    return {
        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/10moUcFrrvPOxz0iroeCZaL90CgooScIJ-5tA6hF9Rmg/edit?gid=434848476",
        "target_name": "Paulo Behling",
        "check_interval_seconds": 30,
        "api_key": "",
        "use_api_v4": False,
        "col_name_idx": 0,
        "col_status_idx": 1,
        "col_vaga_idx": 2,
    }

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ─── Gerenciamento de Estado Persistido ────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_status": "AGUARDAR", "vaga": "Desconhecida", "last_change_time": None}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

# ─── Histórico de Alterações ───────────────────────────────────
def load_audit_logs() -> list:
    if AUDIT_LOG_FILE.exists():
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_audit_log(entry: dict):
    logs = load_audit_logs()
    logs.insert(0, entry)
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:100], f, indent=2, ensure_ascii=False) # Guardar últimos 100

# ─── Extrator de Identificadores da URL ─────────────────────────
def parse_spreadsheet_url(url: str) -> tuple[str, str]:
    # Formato: https://docs.google.com/spreadsheets/d/ID_PLANILHA/edit#gid=ID_PAGINA
    spreadsheet_id = ""
    gid = "0"
    
    # Extrair Spreadsheet ID
    match_id = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match_id:
        spreadsheet_id = match_id.group(1)
        
    # Extrair GID (Sheet ID)
    match_gid = re.search(r"gid=([0-9]+)", url)
    if match_gid:
        gid = match_gid.group(1)
        
    return spreadsheet_id, gid

import re

# ─── Cliente de Rede / Coleta de Dados ──────────────────────────
def fetch_sheet_rows(cfg: dict) -> list[list[str]] | None:
    url = cfg.get("spreadsheet_url", "")
    sheet_id, gid = parse_spreadsheet_url(url)
    
    if not sheet_id:
        st.session_state.last_error = "URL da Planilha inválida. Certifique-se de que contém '/d/ID_PLANILHA'"
        return None
        
    try:
        # Se configurado para usar a API Oficial v4 do Google
        if cfg.get("use_api_v4", False) and cfg.get("api_key", ""):
            api_key = cfg.get("api_key", "")
            # Na API oficial, precisamos do nome da planilha de destino. 
            # Como padrão de fallback, usaremos o range A:C
            api_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A:C?key={api_key}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data.get("values", [])
        
        # Caso contrário, usa a exportação direta para CSV (Super rápida, leve e zero autenticação)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        req = urllib.request.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            csv_content = res.read().decode("utf-8")
            
            # Parsear CSV
            rows = []
            reader = csv.reader(csv_content.splitlines())
            for row in reader:
                rows.append(row)
            return rows
            
    except Exception as e:
        st.session_state.last_error = f"Erro de Conexão: {str(e)}"
        return None

# ─── Inicialização das Variáveis de Sessão (State) ─────────────
for k, v in {
    "next_check_timestamp": 0.0,
    "last_check_time": None,
    "last_error": None,
    "check_count": 0,
    "change_count": 0,
    "trigger_alert": False,
    "alert_payload": {},
    "force_refresh": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Carregar arquivo de configurações
cfg = load_config()

# ─── Componente HTML/JS: Notificação + Som de Alerta ───────────
def inject_alert_components(title: str, body: str):
    """
    Injeta código HTML/JS para disparar duas camadas de alertas locais:
    1. Alerta Sonoro usando Web Audio API do navegador.
    2. Notificação Desktop nativa usando a HTML5 Notification API.
    """
    clean_title = title.replace('"', '\\"')
    clean_body = body.replace('"', '\\"')
    
    components.html(f"""
    <script>
    (function() {{
        // 1. Disparar Beep de Alerta de Alta Prioridade (Três bipes)
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        function beep(freq, start, duration) {{
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
            gain.setValueAtTime(0.4, ctx.currentTime + start);
            gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + duration);
            osc.start(ctx.currentTime + start);
            osc.stop(ctx.currentTime + start + duration);
        }}
        // Sequência sonora de alerta
        beep(880, 0, 0.2);
        beep(1100, 0.25, 0.2);
        beep(880, 0.5, 0.35);

        // 2. Disparar Notificação Nativa do Sistema Operacional (HTML5 Notification API)
        if (!("Notification" in window)) {{
            console.log("Este navegador não suporta notificações desktop.");
            return;
        }}

        function notify() {{
            const notification = new Notification("{clean_title}", {{
                body: "{clean_body}",
                icon: "https://cdn-icons-png.flaticon.com/512/179/179386.png",
                requireInteraction: true
            }});
            
            // Abrir janela caso o usuário clique na notificação
            notification.onclick = function() {{
                window.focus();
                this.close();
            }};
        }}

        if (Notification.permission === "granted") {{
            notify();
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(permission => {{
                if (permission === "granted") {{
                    notify();
                }}
            }});
        }}
    }})();
    </script>
    """, height=0)

# ─── Solicitação Inicial de Permissões de Notificação ───────────
def inject_permission_request():
    components.html("""
    <script>
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }
    </script>
    """, height=0)

# Injetar script para pedir permissão de notificação logo ao abrir a página
inject_permission_request()

# ─── Lógica Principal de Verificação (Check Engine) ─────────────
def run_sheet_check():
    st.session_state.last_error = None
    st.session_state.trigger_alert = False
    
    rows = fetch_sheet_rows(cfg)
    st.session_state.last_check_time = get_local_now().strftime("%d/%m/%Y %H:%M:%S")
    st.session_state.check_count += 1
    
    if rows is None:
        return
        
    target_name = cfg.get("target_name", "Paulo Behling").strip().lower()
    c_name = cfg.get("col_name_idx", 0)
    c_status = cfg.get("col_status_idx", 1)
    c_vaga = cfg.get("col_vaga_idx", 2)
    
    # Encontrar a linha correspondente ao nome
    matching_row = None
    for r in rows:
        if len(r) > max(c_name, c_status, c_vaga):
            cell_name = r[c_name].strip()
            if cell_name.lower() == target_name:
                matching_row = r
                break
                
    if matching_row:
        current_status = matching_row[c_status].strip()
        vaga = matching_row[c_vaga].strip()
        
        # Carregar o último estado salvo em disco
        state = load_state()
        last_status = state.get("last_status", "AGUARDAR").strip()
        
        # LÓGICA DE DETECÇÃO DE TRANSIÇÃO:
        # Quando sai do estado "AGUARDAR" para qualquer outro valor!
        if last_status == "AGUARDAR" and current_status != "AGUARDAR":
            st.session_state.trigger_alert = True
            st.session_state.alert_payload = {
                "nome": matching_row[c_name].strip(),
                "status_anterior": last_status,
                "status_novo": current_status,
                "vaga": vaga,
                "timestamp": get_local_now().isoformat()
            }
            st.session_state.change_count += 1
            
            # Registrar alteração no Histórico do Disco
            save_audit_log({
                "timestamp": get_local_now().isoformat(),
                "nome": matching_row[c_name].strip(),
                "vaga": vaga,
                "status_anterior": last_status,
                "status_novo": current_status
            })
            
            # Tentar notificação local no servidor (Redundância em Python local)
            try:
                from plyer import notification
                notification.notify(
                    title="🎉 Vaga Liberada!",
                    message=f"Olá {matching_row[c_name].strip()}, sua vaga foi atualizada para a VAGA {vaga}!",
                    app_name="Sheets Monitor",
                    timeout=10
                )
            except Exception:
                pass # Se plyer não estiver instalado, a notificação via JS no navegador é 100% suficiente

        # Salvar o estado atualizado para o próximo ciclo
        state["last_status"] = current_status
        state["vaga"] = vaga
        state["last_change_time"] = get_local_now().strftime("%d/%m/%Y %H:%M:%S")
        save_state(state)
        
    else:
        st.session_state.last_error = f"Nome '{cfg.get('target_name')}' não foi encontrado na Coluna {chr(65 + c_name)}."

# ─── Execução Periódica Automatizada ───
if time.time() >= st.session_state.next_check_timestamp or st.session_state.force_refresh:
    st.session_state.force_refresh = False
    run_sheet_check()
    st.session_state.next_check_timestamp = time.time() + cfg.get("check_interval_seconds", 30)

# ─── Painel Lateral (Sidebar) de Configurações ──────────────────
with st.sidebar:
    st.markdown("### ⚙️ Painel de Ajustes")
    st.markdown("---")
    
    st.markdown("**URL de Referência da Planilha**:")
    new_url = st.text_input(
        "Link Google Sheets",
        value=cfg.get("spreadsheet_url", ""),
        help="A planilha precisa ser pública ou compartilhada como 'Leitor' para qualquer pessoa com o link."
    )
    
    st.markdown("**Parâmetro de Busca**:")
    new_target = st.text_input(
        "Nome a Monitorar",
        value=cfg.get("target_name", "Paulo Behling"),
        help="O nome exato a ser procurado na Coluna A da Planilha"
    )
    
    st.markdown("**Intervalo de Consulta**:")
    new_interval = st.number_input(
        "Tempo de Polling (segundos)",
        min_value=5,
        max_value=3600,
        value=int(cfg.get("check_interval_seconds", 30)),
        step=5,
        help="Período em segundos que o Streamlit irá reconsultar a planilha"
    )
    
    with st.expander("📍 Ajuste de Mapeamento de Colunas"):
        new_c_name = st.number_input("Coluna do Nome (A=0, B=1...)", min_value=0, max_value=20, value=cfg.get("col_name_idx", 0))
        new_c_status = st.number_input("Coluna do Status/Onda (A=0, B=1...)", min_value=0, max_value=20, value=cfg.get("col_status_idx", 1))
        new_c_vaga = st.number_input("Coluna da Vaga (A=0, B=1...)", min_value=0, max_value=20, value=cfg.get("col_vaga_idx", 2))

    with st.expander("🔑 Chave oficial da Sheets API v4"):
        use_v4 = st.checkbox("Usar Google API oficial", value=cfg.get("use_api_v4", False))
        api_key = st.text_input("API Key do GCP", value=cfg.get("api_key", ""), type="password")

    st.markdown("---")
    if st.button("💾 Salvar Parâmetros", use_container_width=True, type="primary"):
        cfg["spreadsheet_url"] = new_url
        cfg["target_name"] = new_target
        cfg["check_interval_seconds"] = new_interval
        cfg["col_name_idx"] = new_c_name
        cfg["col_status_idx"] = new_c_status
        cfg["col_vaga_idx"] = new_c_vaga
        cfg["use_api_v4"] = use_v4
        cfg["api_key"] = api_key
        
        save_config(cfg)
        st.success("Configurações gravadas com sucesso!")
        st.session_state.next_check_timestamp = time.time()
        st.session_state.force_refresh = True
        time.sleep(0.5)
        st.rerun()

    if st.button("🔄 Forçar Consulta Agora", use_container_width=True):
        st.session_state.next_check_timestamp = time.time()
        st.session_state.force_refresh = True
        st.rerun()

    st.markdown("---")
    # Regressão de tempo na tela
    remaining_seconds = max(0, int(st.session_state.next_check_timestamp - time.time()))
    st.markdown(
        f"<div style='color:#7f8fb0;font-size:13px;text-align:center'>"
        f"⏱️ Próxima consulta em <h1><b style='color:#00000'>{remaining_seconds}s</b></h1></div>",
        unsafe_allow_html=True,
    )
    if st.session_state.last_check_time:
        st.markdown(
            f"<div style='color:#7f8fb0;font-size:12px;text-align:center;margin-top:4px'>"
            f"Última verificação: {st.session_state.last_check_time}</div>",
            unsafe_allow_html=True,
        )

# ─── Conteúdo Principal do Painel ──────────────────────────────
st.markdown("# 📊 Google Sheets Real-Time Monitor")
st.markdown("Monitor de planilhas inteligente rodando em background com alertas locais nativos de navegador.")
st.markdown("---")

# ─── Seção de Alertas Ativos ──────────────────────────────────
if st.session_state.trigger_alert and st.session_state.alert_payload:
    p = st.session_state.alert_payload
    alert_title = "🎉 SUA VAGA FOI LIBERADA! 🎉"
    alert_body = f"Olá {p['nome']}, sua vaga foi liberada! A vaga atualizada é a VAGA {p['vaga']} (Status: {p['status_novo']})."
    
    # Injetar os bipes sonoros e a notificação push desktop do navegador!
    inject_alert_components(alert_title, alert_body)
    
    # Exibir a caixa de alerta bonita e pulsante
    st.markdown(f"""
    <div class="glow-alert-box">
        🚨 <b>ALTERAÇÃO DE VAGA DETECTADA!</b><br>
        • Nome: {p['nome']}<br>
        • Transição do Status: <span style="text-decoration: line-through; opacity:0.8">{p['status_anterior']}</span> → <b class="highlight-text">{p['status_novo']}</b><br>
        • Vaga Disponível: <b style="font-size: 20px" class="highlight-text">{p['vaga']}</b><br>
        <span style="font-size:12px; opacity:0.7; display:block; margin-top:10px">Disparado em: {datetime.fromisoformat(p['timestamp']).strftime('%d/%m/%Y às %H:%M:%S')}</span>
    </div>
    """, unsafe_allow_html=True)

# Se houver erros de rede, avisa na tela
if st.session_state.last_error:
    st.error(f"⚠️ {st.session_state.last_error}")

# ─── Estatísticas e Métricas Rápidas ────────────────────────────
state = load_state()
c1, c2, c3 = st.columns(3)

# 1. Status do Monitor
monitor_status = f'<div class="status-indicator-dot dot-green"></div>Ativo' if not st.session_state.last_error else f'<div class="status-indicator-dot dot-red"></div>Com Erro'
c1.markdown(f"""
<div class="status-card">
    <div class="card-header">Serviço de Monitoramento</div>
    <div class="card-value" style="font-size: 26px">{monitor_status}</div>
    <div class="card-sub">Polling: {cfg.get('check_interval_seconds')}s</div>
</div>
""", unsafe_allow_html=True)

# 2. Usuário Monitorado
c2.markdown(f"""
<div class="status-card">
    <div class="card-header">Usuário Monitorado</div>
    <div class="card-value" style="font-size: 24px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{cfg.get('target_name')}</div>
    <div class="card-sub">Coluna {chr(65 + cfg.get('col_name_idx'))}</div>
</div>
""", unsafe_allow_html=True)

# 3. Vaga Monitorada
c3.markdown(f"""
<div class="status-card">
    <div class="card-header">Vaga Vinculada</div>
    <div class="card-value highlight-text">{state.get('vaga', 'N/A')}</div>
    <div class="card-sub">Coluna {chr(65 + cfg.get('col_vaga_idx'))}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── Tabs de Organização do Painel ─────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Planilha Completa", "📜 Histórico de Transições", "⚙️ Log de Auditoria do Serviço"])

# ── Tab 1: Exibição da Planilha e Destaque ──
with tab1:
    st.markdown("### 📊 Dados da Planilha do Google")
    st.markdown("As alterações e o usuário monitorado são atualizados dinamicamente a cada loop.")
    
    rows = fetch_sheet_rows(cfg)
    if rows:
        c_name = cfg.get("col_name_idx", 0)
        c_status = cfg.get("col_status_idx", 1)
        c_vaga = cfg.get("col_vaga_idx", 2)
        
        # Construir uma tabela HTML estilizada destacando a linha monitorada
        table_html = """
        <table style="width: 100%; border-collapse: collapse; background-color: #0b0f19; color: #ccd6f6; border-radius: 12px; overflow: hidden; margin-top: 15px;">
            <thead>
                <tr style="background-color: #1f2937; border-bottom: 2px solid #374151; text-align: left;">
                    <th style="padding: 12px 16px;">#</th>
                    <th style="padding: 12px 16px;">Nome Completo (A)</th>
                    <th style="padding: 12px 16px;">Onda/Status (B)</th>
                    <th style="padding: 12px 16px;">Vaga Vinculada (C)</th>
                </tr>
            </thead>
            <tbody>
        """
        
        row_count = 0
        for i, row in enumerate(rows):
            # Filtrar cabeçalhos vazios ou idênticos ao cabeçalho
            if len(row) > max(c_name, c_status, c_vaga):
                nome = row[c_name].strip()
                status = row[c_status].strip()
                vaga = row[c_vaga].strip()
                
                # Ignorar as primeiras linhas se forem cabeçalhos explicativos
                if not nome or nome.lower() in ["nome completo", "nome e senha", "nome"]:
                    continue
                
                row_count += 1
                is_monitored = nome.lower() == cfg.get("target_name", "").strip().lower()
                
                # Estilo se for o usuário selecionado
                if is_monitored:
                    bg_style = "background-color: rgba(100, 255, 218, 0.08); border-left: 5px solid #64ffda;"
                    text_style = "color: #64ffda; font-weight: 600;"
                else:
                    bg_style = "border-bottom: 1px solid #1f2937;"
                    text_style = ""
                    
                table_html += f"""
                <tr style="{bg_style}">
                    <td style="padding: 10px 16px; color:#7f8fb0;">{row_count}</td>
                    <td style="padding: 10px 16px; {text_style}">{nome}</td>
                    <td style="padding: 10px 16px; {text_style}">{status}</td>
                    <td style="padding: 10px 16px; {text_style}">{vaga}</td>
                </tr>
                """
                
        table_html += "</tbody></table>"
        st.markdown(table_html, unsafe_allow_html=True)
    else:
        st.info("💡 A carregar ou sem registros disponíveis na planilha.")

# ── Tab 2: Histórico de Alterações ──
with tab2:
    st.markdown("### 📜 Log de Transições do Status")
    st.markdown("Histórico de alterações na planilha em que o status mudou de 'AGUARDAR' para outro valor.")
    
    logs = load_audit_logs()
    if not logs:
        st.success("🟢 Nenhuma mudança de status detectada até o momento. O usuário ainda está no estado 'AGUARDAR'.")
    else:
        for entry in logs:
            ts = datetime.fromisoformat(entry.get("timestamp")).strftime("%d/%m/%Y às %H:%M:%S")
            st.markdown(f"""
            <div class="audit-row" style="border-left-color: #ff3b30">
                <b>🕐 {ts}</b> — Alteração de <b>{entry.get('nome')}</b><br>
                • Estado anterior: <span style="text-decoration: line-through; opacity:0.8">{entry.get('status_anterior')}</span> → <b class="highlight-text">{entry.get('status_novo')}</b><br>
                • Vaga Concedida: <b class="highlight-text">VAGA {entry.get('vaga')}</b>
            </div>
            """, unsafe_allow_html=True)

# ── Tab 3: Log de Auditoria ──
with tab3:
    st.markdown("### ⚙️ Métricas do Sistema de Monitoramento")
    c1, c2 = st.columns(2)
    c1.metric("Total de Verificações Realizadas", st.session_state.check_count)
    c2.metric("Total de Alertas Gerados", st.session_state.change_count)
    
    st.markdown("---")
    st.markdown("💬 **Modo de Operação do Polling:**")
    st.markdown("""
    - **Execução contínua:** O script reexecuta e atualiza a tela a cada 1 segundo para manter o contador/countdown preciso.
    - **Chamada de Rede Dinâmica:** Uma requisição HTTP ao servidor do Google Sheets ocorre estritamente a cada ciclo configurável.
    - **Baixo Overhead:** Os arquivos de estado de disco previnem a perda de dados caso o servidor seja fechado ou a aba do navegador seja recarregada.
    """)

# ─── Loop de Countdown Dinâmico (Rerun) ──────────────────────────
# Esse comando força o Streamlit a dormir 1 segundo e recarregar, atualizando o contador
time.sleep(1)
st.rerun()
