import streamlit as st
import streamlit.components.v1
import pandas as pd
import numpy as np
import json
import io
import base64
import requests
from datetime import datetime, timezone, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Circle
from reportlab.graphics import renderPDF

st.set_page_config(page_title="Relatórios Onboarding", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-header { background: linear-gradient(135deg, #1a3a5c 0%, #1F4E79 60%, #2e6da4 100%); padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white; }
    .main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .main-header p  { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.95rem; }
    .section-title { font-size: 1.05rem; font-weight: 700; color: #1F4E79; border-left: 4px solid #1F4E79; padding-left: 10px; margin: 1.5rem 0 0.8rem; }
    .metric-card { background: white; border-radius: 10px; padding: 1rem 1.2rem; border: 1px solid #e8edf2; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; }
    .metric-card .label { font-size: 0.78rem; color: #666; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }
    .metric-card .value { font-size: 2rem; font-weight: 700; color: #1F4E79; line-height: 1.2; }
    .metric-card .sub   { font-size: 0.8rem; color: #888; margin-top: 2px; }
    .metric-green .value { color: #1a7a4a; }
    .metric-red   .value { color: #c0392b; }
    .metric-orange .value { color: #d35400; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    div[data-testid="stSidebarNav"] { display: none; }
    footer { visibility: hidden; }
    .footer-custom { text-align: left; color: #999; font-size: 0.78rem; padding: 1rem 0 0.5rem; border-top: 1px solid #eee; margin-top: 2rem; }
</style>
""", unsafe_allow_html=True)

MESES_PT = {
    "2026-01":"Jan/26","2026-02":"Fev/26","2026-03":"Mar/26","2026-04":"Abr/26",
    "2026-05":"Mai/26","2026-06":"Jun/26","2026-07":"Jul/26","2026-08":"Ago/26",
    "2026-09":"Set/26","2026-10":"Out/26","2026-11":"Nov/26","2026-12":"Dez/26",
    "2025-01":"Jan/25","2025-02":"Fev/25","2025-03":"Mar/25","2025-04":"Abr/25",
    "2025-05":"Mai/25","2025-06":"Jun/25","2025-07":"Jul/25","2025-08":"Ago/25",
    "2025-09":"Set/25","2025-10":"Out/25","2025-11":"Nov/25","2025-12":"Dez/25",
    "2024-01":"Jan/24","2024-02":"Fev/24","2024-03":"Mar/24","2024-04":"Abr/24",
    "2024-05":"Mai/24","2024-06":"Jun/24","2024-07":"Jul/24","2024-08":"Ago/24",
    "2024-09":"Set/24","2024-10":"Out/24","2024-11":"Nov/24","2024-12":"Dez/24",
}

def mes_abrev(m): return MESES_PT.get(str(m), str(m))

# ─── PERSISTÊNCIA GITHUB ───────────────────────────────────────────────────────
# Secrets necessários no Streamlit Cloud:
#   GITHUB_TOKEN → Personal Access Token com escopo repo
#   GITHUB_REPO  → "wellpkaraujo/OnboardingFinance"

def _gh_headers():
    token = st.secrets.get("GITHUB_TOKEN", None)
    repo  = st.secrets.get("GITHUB_REPO", None)
    if not token or not repo:
        return None, None, None
    return token, repo, {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

def gh_upload_bytes(filename, data, mensagem="update"):
    try:
        token, repo, headers = _gh_headers()
        if not token: return False, "Secrets não configurados."
        api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
        b64 = base64.b64encode(data).decode()
        r = requests.get(api_url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": mensagem, "content": b64, "branch": "main"}
        if sha: payload["sha"] = sha
        resp = requests.put(api_url, headers=headers, json=payload)
        return resp.status_code in [200, 201], f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

def gh_download_bytes(filename):
    try:
        token, repo, headers = _gh_headers()
        if not token: return None, "Secrets não configurados."
        api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
        r = requests.get(api_url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            if data.get("encoding") == "base64" and data.get("content"):
                return base64.b64decode(data["content"]), ""
            dl = data.get("download_url")
            if dl:
                r2 = requests.get(dl, headers={"Authorization": f"token {token}"})
                return r2.content, ""
        elif r.status_code == 404:
            return None, "não encontrado"
        return None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, str(e)

def gh_delete(filename):
    try:
        token, repo, headers = _gh_headers()
        if not token: return False, "Secrets não configurados."
        api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
        r = requests.get(api_url, headers=headers)
        if r.status_code != 200: return False, "Arquivo não encontrado."
        sha = r.json().get("sha")
        resp = requests.delete(api_url, headers=headers, json={"message": f"Remove {filename}", "sha": sha, "branch": "main"})
        return resp.status_code == 200, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

def df_to_parquet_bytes(df):
    buf = io.BytesIO()

    df = df.copy()

    # Corrige colunas object para evitar erro no parquet
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str)

    df.to_parquet(buf, index=False)

    return buf.getvalue()

def parquet_bytes_to_df(data):
    return pd.read_parquet(io.BytesIO(data))

def salvar_estado_github(salvar_dfs=True):
    try:
        estado = {}

        for key in [
            "nome_arquivo_os",
            "data_upload_os",
            "nome_chamados_implantacao",
            "data_chamados_implantacao",
            "nome_chamados_tech",
            "data_chamados_tech",
            "nome_chamados_produtos",
            "data_chamados_produtos",
            "sla_dias",
            "resumo_executivo",
            "nome_arquivo_os_individual",
            "data_upload_os_individual",
        ]:
            val = st.session_state.get(key)
            if val is not None:
                estado[key] = val

        tab = st.session_state.get("tab_mes_graficos")
        if tab is not None:
            estado["tab_mes_graficos"] = tab.to_dict(orient="records")

        dados = st.session_state.get("dados_os")

        if dados is not None:
            estado["dados_os_meta"] = {
                k: v for k, v in dados.items()
                if k != "df"
            }

        # Salvar meta do módulo individual
        dados_ind = st.session_state.get("dados_os_individual")
        if dados_ind is not None:
            estado["dados_os_individual_meta"] = {
                k: v for k, v in dados_ind.items()
                if k != "df"
            }

        gh_upload_bytes(
            "estado_app.json",
            json.dumps(
                estado,
                ensure_ascii=False,
                default=str
            ).encode(),
            "Atualiza estado"
        )

        if salvar_dfs:

            try:
                for key, filename in [
                    ("df_chamados_implantacao", "df_chamados_implantacao.parquet"),
                    ("df_chamados_tech", "df_chamados_tech.parquet"),
                    ("df_chamados_produtos", "df_chamados_produtos.parquet")
                ]:

                    df = st.session_state.get(key)

                    if df is not None:
                        gh_upload_bytes(
                            filename,
                            df_to_parquet_bytes(df),
                            f"Atualiza {filename}"
                        )

            except Exception as e:
                st.error(f"Erro upload dfs: {e}")

        dados = st.session_state.get("dados_os")

        if dados is not None and dados.get("df") is not None:

            try:
                gh_upload_bytes(
                    "df_os.parquet",
                    df_to_parquet_bytes(dados["df"]),
                    "Atualiza df_os"
                )

                pass  # upload df_os concluído

            except Exception as e:
                st.error(f"Erro upload df_os: {e}")

        # Salvar parquet do módulo individual
        dados_ind = st.session_state.get("dados_os_individual")
        if salvar_dfs and dados_ind is not None and dados_ind.get("df") is not None:
            try:
                gh_upload_bytes(
                    "df_os_individual.parquet",
                    df_to_parquet_bytes(dados_ind["df"]),
                    "Atualiza df_os_individual"
                )
            except Exception as e:
                st.error(f"Erro upload df_os_individual: {e}")

        return True

    except Exception as e:
        st.error(f"ERRO salvar_estado_github: {e}")
        return False

# =============================================================
# COMO USAR
# =============================================================
# 1. Abra seu app.py
# 2. Aperte CTRL + F
# 3. Procure por:
#
#    def carregar_estado_github():
#
# 4. APAGUE a função antiga inteira
# 5. COLE esta função abaixo no lugar
# 6. Commit + Push no GitHub
# =============================================================

def carregar_estado_github():
    try:
        data, err = gh_download_bytes("estado_app.json")
        if data is None:
            return

        estado = json.loads(data.decode())

        # ─────────────────────────────────────────────────────────────
        # Restaurar variáveis simples
        # ─────────────────────────────────────────────────────────────
        for key in [
            "nome_arquivo_os",
            "data_upload_os",
            "nome_chamados_implantacao",
            "data_chamados_implantacao",
            "nome_chamados_tech",
            "data_chamados_tech",
            "nome_chamados_produtos",
            "data_chamados_produtos",
            "sla_dias",
            "resumo_executivo",
            "nome_arquivo_os_individual",
            "data_upload_os_individual",
        ]:
            if key in estado and st.session_state.get(key) is None:
                st.session_state[key] = estado[key]

        # ─────────────────────────────────────────────────────────────
        # Restaurar tabela mensal
        # ─────────────────────────────────────────────────────────────
        if (
            "tab_mes_graficos" in estado
            and st.session_state.get("tab_mes_graficos") is None
        ):
            try:
                st.session_state.tab_mes_graficos = pd.DataFrame(
                    estado["tab_mes_graficos"]
                )
            except:
                pass

        # ─────────────────────────────────────────────────────────────
        # Restaurar dataframes auxiliares
        # ─────────────────────────────────────────────────────────────
        for key, filename in [
            ("df_chamados_implantacao", "df_chamados_implantacao.parquet"),
            ("df_chamados_tech", "df_chamados_tech.parquet"),
            ("df_chamados_produtos", "df_chamados_produtos.parquet"),
        ]:

            if st.session_state.get(key) is None:
                raw, _ = gh_download_bytes(filename)

                if raw:
                    try:
                        st.session_state[key] = parquet_bytes_to_df(raw)
                    except:
                        pass

        # ─────────────────────────────────────────────────────────────
        # Restaurar ORDENS DE SERVIÇO
        # ─────────────────────────────────────────────────────────────
        if st.session_state.get("dados_os") is None:

            raw, _ = gh_download_bytes("df_os.parquet")

            # IMPORTANTE:
            # agora basta existir o parquet
            if raw:

                try:
                    df_os = parquet_bytes_to_df(raw)
                    st.warning(f"df_os carregado: {df_os.shape}")

                    # ==================================================
                    # Recuperar metadata salva
                    # ==================================================
                    meta = estado.get("dados_os_meta", {})

                    # ==================================================
                    # Reconstrução automática se faltar metadata
                    # ==================================================
                    def _find(kw):
                        return next(
                            (
                                c
                                for c in df_os.columns
                                if kw in str(c).lower()
                            ),
                            None,
                        )

                    col_final = meta.get("col_final") or _find("final")
                    col_status = meta.get("col_status") or _find("status")
                    col_cria = meta.get("col_criacao") or _find("cria")
                    col_resp = meta.get("col_responsavel") or _find("respons")
                    col_empresa = meta.get("col_empresa") or _find("empres")

                    col_num_os = (
                        meta.get("col_num_os")
                        or next(
                            (
                                c
                                for c in df_os.columns
                                if any(
                                    x in str(c).lower()
                                    for x in [
                                        "n° os",
                                        "n°os",
                                        "numero",
                                        "n. os",
                                    ]
                                )
                            ),
                            df_os.columns[1]
                            if len(df_os.columns) > 1
                            else df_os.columns[0],
                        )
                    )

                    sla_d = meta.get(
                        "sla_dias",
                        st.session_state.get("sla_dias", 5),
                    )

                    # ==================================================
                    # Reconverter datas
                    # ==================================================
                    if col_cria and col_cria in df_os.columns:
                        df_os[col_cria] = pd.to_datetime(
                            df_os[col_cria],
                            errors="coerce",
                            dayfirst=True,
                        )

                    if col_final and col_final in df_os.columns:
                        df_os[col_final] = pd.to_datetime(
                            df_os[col_final],
                            errors="coerce",
                            dayfirst=True,
                        )

                    # ==================================================
                    # Recriar colunas calculadas
                    # ==================================================
                    if (
                        "Status Calculado" not in df_os.columns
                        and col_status
                        and col_status in df_os.columns
                    ):

                        df_os["Status Calculado"] = df_os[col_status].apply(
                            lambda x: (
                                "Finalizada"
                                if str(x).strip() == "Finalizada"
                                else "Em andamento"
                            )
                        )

                    if (
                        "Dias Uteis" not in df_os.columns
                        and col_cria
                        and col_cria in df_os.columns
                    ):

                        df_os["Dias Uteis"] = df_os.apply(
                            lambda r: dias_uteis(
                                r[col_cria],
                                (
                                    r[col_final]
                                    if col_final and col_final in df_os.columns
                                    else None
                                ),
                            ),
                            axis=1,
                        )

                    if (
                        "Dentro SLA" not in df_os.columns
                        and "Dias Uteis" in df_os.columns
                    ):

                        df_os["Dentro SLA"] = (
                            df_os["Dias Uteis"] <= sla_d
                        )

                    # ==================================================
                    # Persistir no session_state
                    # ==================================================
                    st.session_state.dados_os = {
                        "df": df_os,
                        "col_final": col_final,
                        "col_status": col_status,
                        "col_criacao": col_cria,
                        "col_responsavel": col_resp,
                        "col_empresa": col_empresa,
                        "col_num_os": col_num_os,
                        "sla_dias": sla_d,
                    }
                    st.success("dados_os restaurado")
                    
                except Exception as e:
                    st.warning(f"Erro ao restaurar df_os: {e}")

        # ─────────────────────────────────────────────────────────────
        # Restaurar DESEMPENHO INDIVIDUAL
        # ─────────────────────────────────────────────────────────────
        if st.session_state.get("dados_os_individual") is None:
            raw_ind, _ = gh_download_bytes("df_os_individual.parquet")
            if raw_ind:
                try:
                    df_ind = parquet_bytes_to_df(raw_ind)
                    meta_ind = estado.get("dados_os_individual_meta", {})

                    def _find_ind(kw):
                        return next((c for c in df_ind.columns if kw.lower() in str(c).lower()), None)

                    # Reconverter datas
                    for ck in ["col_criacao", "col_final"]:
                        cn = meta_ind.get(ck) or _find_ind("criacao" if ck == "col_criacao" else "finalizacao")
                        if cn and cn in df_ind.columns:
                            df_ind[cn] = pd.to_datetime(df_ind[cn], errors="coerce")

                    # Recriar colunas calculadas se necessário
                    if "Status Calculado" not in df_ind.columns:
                        col_s = meta_ind.get("col_status") or _find_ind("status")
                        if col_s and col_s in df_ind.columns:
                            df_ind["Status Calculado"] = df_ind[col_s].apply(
                                lambda x: "Finalizada" if str(x).strip().upper() in ["FINALIZADA","FINALIZADO"] else "Em andamento"
                            )
                    if "Dias Uteis" not in df_ind.columns:
                        col_d = _find_ind("periodo_responsabilidade_em_dia") or _find_ind("total_dias")
                        if col_d and col_d in df_ind.columns:
                            df_ind["Dias Uteis"] = pd.to_numeric(df_ind[col_d], errors="coerce").fillna(0).astype(int)
                    sla_d_ind = meta_ind.get("sla_dias", st.session_state.get("sla_dias", 5))
                    if "Dentro SLA" not in df_ind.columns and "Dias Uteis" in df_ind.columns:
                        df_ind["Dentro SLA"] = df_ind["Dias Uteis"] <= sla_d_ind

                    st.session_state.dados_os_individual = {**meta_ind, "df": df_ind}
                except Exception as e:
                    st.warning(f"Erro ao restaurar df_os_individual: {e}")

    except Exception as e:
        st.warning(f"Erro ao carregar estado do GitHub: {e}")



# ─── DICIONÁRIOS ──────────────────────────────────────────────────────────────

CLASSIFICACAO_IMPLANTACAO_PADRAO = {
    "Incidente - Erro de API":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de autenticação API":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de requisição":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de processamento":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro na Cron":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo não recebido":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo não enviado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro na geração de arquivo":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Correção de Billing":{"tipo":"Incidente","sla":"24:00"},
    "Incidente - Falha de conexão":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Instabilidade de comunicação":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de autenticação":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Timeout de integração":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Tarefa Agendada":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro de mapeamento":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro no portal":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de acesso":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo rejeitado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo duplicado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Inconsistência de processamento":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro no Webservice":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de autenticação":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de requisição Webservice":{"tipo":"Incidente","sla":"08:00"},
    "Solicitação - Configuração de API":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de integração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Analise de arquivo":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de envio":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de recebimento":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Analise de Billing":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastrar o Billing":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastro de parceiro":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de parceiro":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastro de documento":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de cadastro":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de conexão":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de conectividade":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastro de configuração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de configuração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ativação / Inativação":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ajuste de parâmetros":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de caixa postal":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Relatório de configuração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ajuste de mapeamento":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Criação de novo mapa":{"tipo":"Solicitação","sla":"24:00"},
    "Solicitação - Alteração de layout":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Inclusão de campo":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Validação de layout":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Inclusão de mapa":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ajuste de funcionalidade":{"tipo":"Solicitação","sla":"16:00"},
    "Melhoria - Solicitação de melhoria":{"tipo":"Melhoria - Solicitação de Melhoria","sla":"24:00"},
    "Solicitação - Criar acesso":{"tipo":"Solicitação","sla":"08:00"},
    "Solicitação - Reprocessamento de arquivo":{"tipo":"Solicitação","sla":"08:00"},
    "Solicitação - Alteração de integração Webservice":{"tipo":"Solicitação","sla":"16:00"},
    "Reabertura":{"tipo":"Incidente","sla":None},
    "Analise de Billing":{"tipo":"Incidente","sla":None},
    "Corrigir Billing":{"tipo":"Incidente","sla":None},
    "Correção de custo":{"tipo":"Incidente","sla":None},
    "Falha no processamento":{"tipo":"Incidente","sla":None},
    "Nomenclatura do cliente incorreta":{"tipo":"Incidente","sla":None},
    "Nomenclatura do banco incorreta":{"tipo":"Incidente","sla":None},
    "Deploy não realizado do INI":{"tipo":"Incidente","sla":None},
    "Dados da abertura de relacionamento incorreto":{"tipo":"Incidente","sla":None},
    "Configuraçao sem vinculo com abertura":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Arquivo com layout diferente da abertura de relacionamento":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Vinculo da configuração incorreto":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Arquivo fora do layout":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Arquivo com caracteres especiais":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Arquivo com informações faltantes":{"tipo":"Incidente","sla":None},
    "Analise de arquivo - Arquivo vazio":{"tipo":"Incidente","sla":None},
    "Erro de transmissão de remessa em produção":{"tipo":"Incidente","sla":None},
    "Erro de transmissão de retorno em produção":{"tipo":"Incidente","sla":None},
    "Erro de transmissão de remessa em Homologação":{"tipo":"Incidente","sla":None},
    "Erro de transmissão de retorno em Homologação":{"tipo":"Incidente","sla":None},
    "E-mail interno":{"tipo":"Solicitação","sla":None},
    "Criar configuração":{"tipo":"Solicitação","sla":None},
    "Criar acesso":{"tipo":"Solicitação","sla":None},
    "Consultar trafego":{"tipo":"Solicitação","sla":None},
    "Relatorio de configurações":{"tipo":"Solicitação","sla":None},
    "Criar caixa postal":{"tipo":"Solicitação","sla":None},
    "Reset de senha":{"tipo":"Solicitação","sla":None},
    "Consultar Billing":{"tipo":"Solicitação","sla":None},
    "Inativar configuração":{"tipo":"Solicitação","sla":None},
    "Reativar configuração":{"tipo":"Solicitação","sla":None},
    "Projeto em andamento (de 0 a 50 contas)":{"tipo":"Solicitação","sla":None},
}

CLASSIFICACAO_TECH_PADRAO = {
    "Incidente - Erro de API":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de autenticação API":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de processamento (Open Finance)":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro na Cron":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo não recebido":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo não enviado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro na geração de arquivo":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Correção de Billing":{"tipo":"Incidente","sla":"24:00"},
    "Incidente - Falha de conexão":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Instabilidade de comunicação":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de autenticação":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Timeout de integração":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Tarefa Agendada":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro de mapeamento":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro no portal":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Problema de acesso":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo rejeitado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Arquivo duplicado":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de processamento":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Erro no Webservice":{"tipo":"Incidente","sla":"08:00"},
    "Incidente - Falha de autenticação":{"tipo":"Incidente","sla":"08:00"},
    "Solicitação - Analise de arquivo":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de envio":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Configuração de recebimento":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Inclusão de Certificados ou Chaves":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Tratativas de Arquivos":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Analise de Billing":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastrar o Billing":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastro de parceiro":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de parceiro":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Cadastro de configuração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Alteração de configuração":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ativação / Inativação":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Ajuste de parâmetros":{"tipo":"Solicitação","sla":"16:00"},
    "Solicitação - Criar acesso":{"tipo":"Solicitação","sla":"08:00"},
    "Solicitação - Falta de Análise / Mal Uso da Plataforma":{"tipo":"Solicitação","sla":"08:00"},
    "Solicitação - Reprocessamento de arquivo":{"tipo":"Solicitação","sla":"08:00"},
    "Solicitação - Certificado (alterar/Incluir/Dúvidas)":{"tipo":"Solicitação","sla":"08:00"},
    "Melhoria - Solicitação de melhoria":{"tipo":"Melhoria - Solicitação de Melhoria","sla":"24:00"},
}

CLASSIFICACAO_PRODUTOS_PADRAO = {
    "Correção de mapa / Bug - Produção":{"tipo":"Incidente","sla":"04:00"},
    "Correção de mapa / Bug - Homologação":{"tipo":"Incidente","sla":"16:00"},
    "Indisponibilidade de ambiente":{"tipo":"Incidente","sla":"02:00"},
    "Intermitência/lentidão":{"tipo":"Incidente","sla":"04:00"},
    "Consultar log - Incidente não identificado / Impacto de alta criticidade":{"tipo":"Incidente","sla":"08:00"},
    "Alteração de mapa / Melhoria":{"tipo":"Solicitação","sla":"08:00"},
    "Analise de mapa":{"tipo":"Solicitação","sla":"08:00"},
    "Consultar base de dados core documentos":{"tipo":"Solicitação","sla":"16:00"},
    "Consultar Especificação":{"tipo":"Solicitação","sla":"16:00"},
    "Consultar existencia de mapa":{"tipo":"Solicitação","sla":"16:00"},
}

# ─── SESSION STATE ─────────────────────────────────────────────────────────────

_defaults = {
    "dic_implantacao": dict(CLASSIFICACAO_IMPLANTACAO_PADRAO),
    "dic_tech": dict(CLASSIFICACAO_TECH_PADRAO),
    "dic_produtos": dict(CLASSIFICACAO_PRODUTOS_PADRAO),
    "sla_dias": 5, "tab_mes_graficos": None, "nome_arquivo_os": None,
    "data_upload_os": None, "resumo_executivo": None, "dados_os": None,
    "historico_2025_ativo": False, "df_chamados_implantacao": None,
    "df_chamados_tech": None, "df_chamados_produtos": None,
    "nome_chamados_implantacao": None, "nome_chamados_tech": None, "nome_chamados_produtos": None,
    "data_chamados_implantacao": None, "data_chamados_tech": None, "data_chamados_produtos": None,
    "_estado_carregado": False,
    "fluxo_os_inicio_salvo": None,
    "fluxo_os_fim_salvo": None,
    "perf_resp_inicio_salvo": None,
    "perf_resp_fim_salvo": None,
    "dados_os_individual": None,
    "nome_arquivo_os_individual": None,
    "data_upload_os_individual": None,
    "di_resp_inicio_salvo": None,
    "di_resp_fim_salvo": None,
}
for k, v in _defaults.items():
    if k not in st.session_state: st.session_state[k] = v

if not st.session_state["_estado_carregado"]:
    with st.spinner("🔄 Carregando dados salvos..."):
        carregar_estado_github()
    st.session_state["_estado_carregado"] = True

# ─── FUNÇÕES AUXILIARES ────────────────────────────────────────────────────────

def estilizar(df):
    numeric_cols = set(df.select_dtypes(include="number").columns.tolist())
    pct_cols = set()
    for c in df.columns:
        if str(c).startswith("%") or str(c).endswith("%"): pct_cols.add(c)
        elif df[c].dtype == object and len(df[c].dropna()) > 0:
            if df[c].dropna().astype(str).str.match(r"^\d+%$").all(): pct_cols.add(c)
    center_cols = numeric_cols | pct_cols
    html = """<style>.custom-table{width:100%;border-collapse:collapse;font-family:'Inter',sans-serif;font-size:0.875rem;}
    .custom-table th{background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;}
    .custom-table td{padding:7px 12px;border-bottom:1px solid #e8edf2;}
    .custom-table tr:nth-child(even) td{background:#f5f8fc;}.custom-table tr:hover td{background:#eaf1fb;}
    .custom-table .num{text-align:center;}.custom-table .txt{text-align:left;}
    </style><table class="custom-table"><thead><tr>"""
    for col in df.columns: html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for _, row in df.iterrows():
        html += "<tr>"
        for col in df.columns:
            cls = "num" if col in center_cols else "txt"
            val = row[col]
            if pd.isna(val): val = ""
            html += f'<td class="{cls}">{val}</td>'
        html += "</tr>"
    html += "</tbody></table>"
    return html

def estilizar_tab_mes(tab_mes):
    total_fin = int(tab_mes["Finalizadas"].sum())
    total_dentro = int(tab_mes["Dentro"].sum())
    total_fora = int(tab_mes["Fora"].sum())
    media_dentro = round(total_dentro/total_fin*100) if total_fin > 0 else 0
    media_fora = round(total_fora/total_fin*100) if total_fin > 0 else 0
    linhas = ""
    for i, (_, row) in enumerate(tab_mes.iterrows()):
        bg = ' style="background:#f5f8fc;"' if i % 2 == 1 else ""
        linhas += f"""<tr{bg}>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:left;">{row['Mês']}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:center;">{int(row['Finalizadas'])}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:center;">{int(row['Dentro'])}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:center;">{int(row['Dentro_pct'])}%</td>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:center;">{int(row['Fora'])}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #e8edf2;text-align:center;">{int(row['Fora_pct'])}%</td>
        </tr>"""
    return f"""<table style="width:100%;border-collapse:collapse;font-family:'Inter',sans-serif;font-size:0.875rem;">
    <thead><tr>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">Mês</th>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">Finalizadas</th>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">Dentro do SLA</th>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">% Dentro do SLA</th>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">Fora do SLA</th>
        <th style="background:#1F4E79;color:white;text-align:center;padding:8px 12px;font-weight:600;">% Fora do SLA</th>
    </tr></thead><tbody>{linhas}
        <tr>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:left;">Total</td>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:center;">{total_fin}</td>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:center;">{total_dentro}</td>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:center;">{media_dentro}%</td>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:center;">{total_fora}</td>
            <td style="padding:7px 12px;background:#1F4E79;color:white;font-weight:600;text-align:center;">{media_fora}%</td>
        </tr>
    </tbody></table>"""

def classificar(m, dic):
    m_strip = str(m).strip(); m_lower = m_strip.lower()
    if m_strip in dic: return dic[m_strip]["tipo"]
    if m_lower.startswith("incidente"): return "Incidente"
    if m_lower.startswith("solicitação") or m_lower.startswith("solicitacao"): return "Solicitação"
    if m_lower.startswith("melhoria"): return "Melhoria - Solicitação de Melhoria"
    if any(x in m_lower for x in ["erro","analise","corrigir","reabertura"]): return "Incidente"
    return "Solicitação"

def analisar_chamados(df, dic):
    df = df.copy()
    col_data = None
    for c in df.columns:
        cl = str(c).lower().strip()
        if any(kw in cl for kw in ["criação do ticket","criacao do ticket","data criação","data criacao","data de criação","data de abertura","aberto em","created","criação"]):
            col_data = c; break
    if col_data is None:
        for c in df.columns:
            cl = str(c).lower().strip()
            if "data" in cl or "cria" in cl: col_data = c; break
    if col_data is None:
        for c in df.columns:
            sample = pd.to_datetime(df[c], dayfirst=True, errors="coerce").dropna()
            if len(sample) > len(df) * 0.5: col_data = c; break
    if col_data is None: raise KeyError("Não foi possível localizar a coluna de data de criação do ticket.")
    if "Motivo de abertura BU" not in df.columns: raise KeyError(f"Coluna 'Motivo de abertura BU' não encontrada.")
    if col_data != "Criação do Ticket": df = df.rename(columns={col_data: "Criação do Ticket"})
    df = df.reset_index(drop=True).loc[:, ~df.columns.duplicated()]
    df["Criação do Ticket"] = pd.to_datetime(df["Criação do Ticket"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Criação do Ticket"]).reset_index(drop=True)
    df["Mes"] = df["Criação do Ticket"].dt.to_period("M").astype(str)
    df["Tipo"] = df["Motivo de abertura BU"].apply(lambda m: classificar(m, dic))
    return df

def dias_uteis(inicio, fim):
    if pd.isna(inicio): return 0
    if pd.isna(fim): fim = pd.Timestamp.today()
    return int(np.busday_count(inicio.date(), (fim + pd.Timedelta(days=1)).date()))

def analisar_os(file_content, sla_dias):
    raw = pd.read_excel(io.BytesIO(file_content), header=None)
    header_row = None
    for i, row in raw.iterrows():
        if row.astype(str).str.lower().str.contains("status").any(): header_row = i; break
    if header_row is None: return None, "Não foi possível localizar o cabeçalho na planilha."
    df = pd.read_excel(io.BytesIO(file_content), header=header_row)
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]; df.columns = df.columns.str.strip()
    col_os = df.columns[1]; df = df.drop_duplicates(subset=[col_os])
    def find(kw): return next((c for c in df.columns if kw in str(c).lower()), None)
    col_status = find("status"); col_criacao = find("cria"); col_final = find("final")
    col_responsavel = find("respons")
    col_num_os = next((c for c in df.columns if any(x in str(c).lower() for x in ["n° os","n°os","numero","n. os"])), col_os)
    col_empresa = find("empres")
    if not col_criacao or not col_status: return None, "Colunas necessárias não encontradas."
    df[col_criacao] = pd.to_datetime(df[col_criacao], dayfirst=True, errors="coerce")
    if col_final: df[col_final] = pd.to_datetime(df[col_final], dayfirst=True, errors="coerce")
    df["Status Calculado"] = df[col_status].apply(lambda x: "Finalizada" if str(x).strip() == "Finalizada" else "Em andamento")
    df["Dias Uteis"] = df.apply(lambda r: dias_uteis(r[col_criacao], r[col_final] if col_final else None), axis=1)
    df["Dentro SLA"] = df["Dias Uteis"] <= sla_dias
    return df, None

def analisar_os_individual(file_content, sla_dias):
    """
    Analisa planilha de OS no formato exportado pelo sistema interno
    (colunas snake_case: os_numero, os_usuario_responsavel_nome, os_status_nome,
    os_data_criacao, os_data_finalizacao, periodo_responsabilidade_em_dia, etc.)
    Também suporta o formato legado com busca de cabeçalho por 'status'.
    """
    import io as _io

    def _excel_serial_to_ts(val):
        try:
            if pd.isna(val): return pd.NaT
            if isinstance(val, (pd.Timestamp, datetime)): return pd.Timestamp(val)
            return pd.Timestamp('1899-12-30') + pd.Timedelta(days=float(val))
        except:
            return pd.NaT

    # ── Tentar formato snake_case primeiro ──────────────────────────────────
    try:
        df_raw = pd.read_excel(_io.BytesIO(file_content), header=0)
        df_raw.columns = df_raw.columns.str.strip()

        # Detectar se é o formato snake_case verificando colunas-chave
        _cols_lower = [c.lower() for c in df_raw.columns]
        is_snake = any("os_numero" in c or "os_usuario_responsavel" in c for c in _cols_lower)

        if is_snake:
            df = df_raw.copy()

            # Mapear colunas para nomes padronizados
            def _col(kws):
                for kw in kws:
                    found = next((c for c in df.columns if kw.lower() in c.lower()), None)
                    if found: return found
                return None

            col_num_os     = _col(["os_numero"])
            col_status     = _col(["os_status_nome"])
            col_criacao    = _col(["os_data_criacao"])
            col_final      = _col(["os_data_finalizacao"])
            col_responsavel = _col(["os_usuario_responsavel_nome"])
            col_empresa    = _col(["empresa_razao_social", "grupo_empresa"])
            col_banco      = _col(["banco_nome"])
            col_dias       = _col(["periodo_responsabilidade_em_dia_time", "periodo_responsabilidade_em_dia", "total_dias_os"])

            if not col_status or not col_num_os:
                return None, "Colunas obrigatórias (os_numero, os_status_nome) não encontradas."

            # Remover duplicatas
            df = df.drop_duplicates(subset=[col_num_os]).reset_index(drop=True)

            # Converter datas (podem ser seriais numéricos ou datetime)
            for col_d in [col_criacao, col_final]:
                if col_d and col_d in df.columns:
                    df[col_d] = df[col_d].apply(_excel_serial_to_ts)

            # Status Calculado
            df["Status Calculado"] = df[col_status].apply(
                lambda x: "Finalizada" if str(x).strip().upper() == "FINALIZADA" else "Em andamento"
            )

            # Dias Úteis — usar coluna existente se disponível, senão calcular
            if col_dias and col_dias in df.columns:
                df["Dias Uteis"] = pd.to_numeric(df[col_dias], errors="coerce").fillna(0).astype(int)
            elif col_criacao and col_final:
                df["Dias Uteis"] = df.apply(
                    lambda r: dias_uteis(r[col_criacao], r[col_final]), axis=1
                )
            else:
                df["Dias Uteis"] = 0

            df["Dentro SLA"] = df["Dias Uteis"] <= sla_dias

            return df, None, {
                "col_num_os": col_num_os,
                "col_status": col_status,
                "col_criacao": col_criacao,
                "col_final": col_final,
                "col_responsavel": col_responsavel,
                "col_empresa": col_empresa,
                "col_banco": col_banco,
                "sla_dias": sla_dias,
                "formato": "snake_case",
            }

    except Exception as e_snake:
        pass  # fallback para formato legado

    # ── Fallback: formato legado (busca cabeçalho por "status") ────────────
    try:
        raw = pd.read_excel(_io.BytesIO(file_content), header=None)
        header_row = None
        for i, row in raw.iterrows():
            if row.astype(str).str.lower().str.contains("status").any():
                header_row = i; break
        if header_row is None:
            return None, "Não foi possível localizar o cabeçalho na planilha.", {}

        df = pd.read_excel(_io.BytesIO(file_content), header=header_row)
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        col_os = df.columns[1]
        df = df.drop_duplicates(subset=[col_os])

        def find(kw): return next((c for c in df.columns if kw in str(c).lower()), None)
        col_status    = find("status")
        col_criacao   = find("cria")
        col_final     = find("final")
        col_resp      = find("respons")
        col_empresa   = find("empres")
        col_num_os    = next((c for c in df.columns if any(x in str(c).lower() for x in ["n° os","n°os","numero","n. os"])), col_os)

        if not col_criacao or not col_status:
            return None, "Colunas necessárias não encontradas.", {}

        df[col_criacao] = pd.to_datetime(df[col_criacao], dayfirst=True, errors="coerce")
        if col_final:
            df[col_final] = pd.to_datetime(df[col_final], dayfirst=True, errors="coerce")

        df["Status Calculado"] = df[col_status].apply(
            lambda x: "Finalizada" if str(x).strip() == "Finalizada" else "Em andamento"
        )
        df["Dias Uteis"] = df.apply(
            lambda r: dias_uteis(r[col_criacao], r[col_final] if col_final else None), axis=1
        )
        df["Dentro SLA"] = df["Dias Uteis"] <= sla_dias

        return df, None, {
            "col_num_os": col_num_os,
            "col_status": col_status,
            "col_criacao": col_criacao,
            "col_final": col_final,
            "col_responsavel": col_resp,
            "col_empresa": col_empresa,
            "col_banco": None,
            "sla_dias": sla_dias,
            "formato": "legado",
        }

    except Exception as e_leg:
        return None, f"Erro ao processar planilha: {e_leg}", {}



def upload_pdf_github(pdf_bytes, nome_arq="", data_arq=""):
    ok, err = gh_upload_bytes("status_atual.pdf", pdf_bytes, "Atualiza status_atual.pdf")
    if ok:
        info = {"nome_arquivo": nome_arq, "data_upload": data_arq}
        gh_upload_bytes("status_info.json", json.dumps(info, ensure_ascii=False).encode(), "Atualiza info")
    return ok, err

def baixar_pdf_github():
    data, err = gh_download_bytes("status_atual.pdf")
    if data: return data, None
    return None, "Nenhum PDF encontrado." if "não encontrado" in err else err

def upload_pdf_chamados_github(pdf_bytes, area_key, nome_arq="", data_arq=""):
    filename = f"status_chamados_{area_key}.pdf"
    ok, err = gh_upload_bytes(filename, pdf_bytes, f"Atualiza {filename}")
    if ok:
        info = {"nome_arquivo": nome_arq, "data_upload": data_arq}
        gh_upload_bytes(f"status_chamados_{area_key}_info.json", json.dumps(info, ensure_ascii=False).encode(), f"Atualiza info {area_key}")
    return ok, err

def baixar_pdf_chamados_github(area_key):
    data, err = gh_download_bytes(f"status_chamados_{area_key}.pdf")
    if data: return data, None
    return None, "Nenhum PDF encontrado." if "não encontrado" in err else err

def buscar_status_info_github():
    data, _ = gh_download_bytes("status_info.json")
    if data:
        try: return json.loads(data.decode())
        except: pass
    return None

def baixar_base_historica_github():
    data, err = gh_download_bytes("OS_Base_Unificada_Jan25_Abr26.xlsx")
    return data, err if not data else None


# ─── EXCEL ─────────────────────────────────────────────────────────────────────

def gerar_excel_chamados(df, meses, meses_label):
    output = io.BytesIO()
    tipo = df["Tipo"].value_counts(); total = len(df)
    mes_atual = meses[-1]; mes_atual_lbl = mes_abrev(mes_atual)
    col_motivo = "Motivo de abertura BU"
    tem_sla = "Dentro do SLA" in df.columns
    if tem_sla:
        sla = df.groupby("Mes").agg(Total=("Mes","count"),
            Dentro=("Dentro do SLA",lambda x:((x=="Dentro")|(x=="Sem SLA")).sum()),
            Fora=("Dentro do SLA",lambda x:(x=="Fora").sum())).reset_index()
        sla["% Dentro"]=(sla["Dentro"]/sla["Total"]).round(4); sla["% Fora"]=(sla["Fora"]/sla["Total"]).round(4)
    else:
        sla = df.groupby("Mes").agg(Total=("Mes","count")).reset_index()
        sla["Dentro"]=sla["Total"]; sla["Fora"]=0; sla["% Dentro"]=1.0; sla["% Fora"]=0.0
    sla["Mes"]=sla["Mes"].apply(mes_abrev)
    classificacao = pd.DataFrame({"Incidentes":[tipo.get("Incidente",0)],"Solicitações":[tipo.get("Solicitação",0)],
        "Melhorias":[tipo.get("Melhoria - Solicitação de Melhoria",0)],
        "% Incidentes":[round(tipo.get("Incidente",0)/total,4) if total else 0],
        "% Solicitações":[round(tipo.get("Solicitação",0)/total,4) if total else 0],
        "% Melhorias":[round(tipo.get("Melhoria - Solicitação de Melhoria",0)/total,4) if total else 0]})
    def top3_df(df_f, ml, mll):
        if len(df_f)==0: return pd.DataFrame()
        top=df_f[col_motivo].value_counts().head(3).index.tolist(); rows=[]
        for m in top:
            row={"Motivo":m}; tot=0
            for mes,lbl in zip(ml,mll):
                q=df_f[(df_f["Mes"]==mes)&(df_f[col_motivo]==m)].shape[0]; row[lbl]=q; tot+=q
            row["Total"]=tot; rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    df_sol_all=df[df["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
    df_inc_all=df[df["Tipo"]=="Incidente"]
    df_mes_a=df[df["Mes"]==mes_atual]
    df_sol_mes_a=df_mes_a[df_mes_a["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
    df_inc_mes_a=df_mes_a[df_mes_a["Tipo"]=="Incidente"]
    top_sol_pessoas=df["Criado por"].value_counts().head(3).index if "Criado por" in df.columns else []
    rows_sol_p=[]
    for s in top_sol_pessoas:
        row={"Solicitante":s}; tot=0
        for mes,lbl in zip(meses,meses_label):
            q=df[(df["Mes"]==mes)&(df["Criado por"]==s)].shape[0]; row[lbl]=q; tot+=q
        row["Total"]=tot; rows_sol_p.append(row)
    rows_mot=[]
    for s in top_sol_pessoas:
        temp=df[df["Criado por"]==s]; top_m=temp[col_motivo].value_counts().head(3)
        rows_mot.append({"Solicitante":s,
            "1º Motivo":top_m.index[0] if len(top_m)>0 else "-","Qtd 1":top_m.iloc[0] if len(top_m)>0 else 0,
            "2º Motivo":top_m.index[1] if len(top_m)>1 else "-","Qtd 2":top_m.iloc[1] if len(top_m)>1 else 0,
            "3º Motivo":top_m.index[2] if len(top_m)>2 else "-","Qtd 3":top_m.iloc[2] if len(top_m)>2 else 0})
    def escrever_bloco(writer, sheet, df_b, titulo, start):
        pd.DataFrame([[titulo]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
        if len(df_b)>0: df_b.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(df_b)+3
        else: pd.DataFrame([["Sem dados"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=3
        return start
    with pd.ExcelWriter(output,engine="openpyxl") as writer:
        sheet="Relatorio"; start=0
        sla.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(sla)+4
        classificacao.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=4
        start=escrever_bloco(writer,sheet,top3_df(df_inc_all,meses,meses_label),"Top 3 Motivos de Incidentes — Período Completo",start)
        start=escrever_bloco(writer,sheet,top3_df(df_inc_mes_a,[mes_atual],[mes_atual_lbl]),f"Top 3 Motivos de Incidentes — {mes_atual_lbl}",start)
        start=escrever_bloco(writer,sheet,top3_df(df_sol_all,meses,meses_label),"Top 3 Motivos de Solicitações — Período Completo",start)
        start=escrever_bloco(writer,sheet,top3_df(df_sol_mes_a,[mes_atual],[mes_atual_lbl]),f"Top 3 Motivos de Solicitações — {mes_atual_lbl}",start)
        if rows_sol_p:
            start=escrever_bloco(writer,sheet,pd.DataFrame(rows_sol_p),"Top 3 Solicitantes",start)
            start=escrever_bloco(writer,sheet,pd.DataFrame(rows_mot),"Principais Motivos por Solicitante",start)
        ws=writer.sheets[sheet]
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value,float) and cell.value<=1.0: cell.number_format="0%"
    output.seek(0); return output

def gerar_excel_os(df, sla_dias, col_num_os, col_responsavel, col_empresa, col_status, col_final):
    output=io.BytesIO()
    finalizadas=df[df["Status Calculado"]=="Finalizada"].copy()
    andamento=df[df["Status Calculado"]!="Finalizada"].copy()
    dentro_and=andamento[andamento["Dentro SLA"]]; fora_and=andamento[~andamento["Dentro SLA"]]
    pct_dentro=round(len(dentro_and)/len(andamento)*100) if len(andamento)>0 else 0
    pct_fora=round(len(fora_and)/len(andamento)*100) if len(andamento)>0 else 0
    resumo_df=pd.DataFrame([
        {"Descrição":"Quantidade de OS em andamento:","Valor":len(andamento),"":""},
        {"Descrição":"Quantidade de OS recebidas:","Valor":len(df),"":""},
        {"Descrição":"Quantidade de OS finalizadas no total:","Valor":len(finalizadas),"":""},
        {"Descrição":"","Valor":"","":""},
        {"Descrição":f"Dentro do SLA (≤{sla_dias} dias úteis):","Valor":len(dentro_and),"":f"{pct_dentro}%"},
        {"Descrição":f"Fora do SLA (>{sla_dias} dias úteis):","Valor":len(fora_and),"":f"{pct_fora}%"},])
    tabela=finalizadas.groupby(finalizadas[col_final].dt.to_period("M")).agg(Finalizadas=(col_final,"count"),Dentro=("Dentro SLA","sum")).reset_index()
    tabela.columns=["Mes","Finalizadas","Dentro do SLA"]
    tabela["Fora do SLA"]=tabela["Finalizadas"]-tabela["Dentro do SLA"]
    tabela["% Dentro do SLA"]=(tabela["Dentro do SLA"]/tabela["Finalizadas"]).round(4)
    tabela["% Fora do SLA"]=(tabela["Fora do SLA"]/tabela["Finalizadas"]).round(4)
    tabela["Mês"]=tabela["Mes"].apply(lambda m:mes_abrev(str(m)))
    tf=tabela["Finalizadas"].sum(); td=tabela["Dentro do SLA"].sum(); tfo=tabela["Fora do SLA"].sum()
    total_row=pd.DataFrame([{"Mês":"Total","Finalizadas":tf,"Dentro do SLA":td,
        "% Dentro do SLA":round(td/tf,4) if tf>0 else 0,"Fora do SLA":tfo,"% Fora do SLA":round(tfo/tf,4) if tf>0 else 0}])
    tabela_excel=pd.concat([tabela[["Mês","Finalizadas","Dentro do SLA","% Dentro do SLA","Fora do SLA","% Fora do SLA"]],total_row],ignore_index=True)
    col_banco=next((c for c in df.columns if "banco" in str(c).lower()),None)
    col_cria_os=next((c for c in df.columns if "cria" in str(c).lower()),None)
    cef_tab=pd.DataFrame()
    if col_banco and col_cria_os:
        cef=df[df[col_banco].astype(str).str.upper().str.strip()=="CAIXA ECONOMICA FEDERAL"].copy()
        if len(cef)>0:
            cef["Mes_Criacao"]=pd.to_datetime(cef[col_cria_os],dayfirst=True,errors="coerce").dt.to_period("M")
            ct=cef.groupby("Mes_Criacao").agg(Total=("Mes_Criacao","count"),Media_Dias=("Dias Uteis","mean")).reset_index().sort_values("Mes_Criacao")
            ct["Mês"]=ct["Mes_Criacao"].apply(lambda m:mes_abrev(str(m)))
            ct["Média de Dias de Conclusão"]=ct["Media_Dias"].round(0).astype(int)
            cef_tab=ct.rename(columns={"Total":"Total OS"})[["Mês","Total OS","Média de Dias de Conclusão"]]
    with pd.ExcelWriter(output,engine="openpyxl") as writer:
        start=0; sheet="OS"
        pd.DataFrame([["RESUMO GERAL"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
        resumo_df.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(resumo_df)+4
        pd.DataFrame([["OS Finalizadas por Mês"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
        tabela_excel.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(tabela_excel)+4
        if col_responsavel:
            an=andamento.groupby(col_responsavel).size().reset_index(name="OS em Andamento")
            an.columns=["Responsável","OS em Andamento"]; an=an.sort_values("OS em Andamento",ascending=False).reset_index(drop=True)
            pd.DataFrame([["Ordens de Serviços em Andamento por Responsável"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
            an.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(an)+4
        cols_fora=[col_num_os]
        if col_responsavel: cols_fora.append(col_responsavel)
        if col_status: cols_fora.append(col_status)
        cols_fora.append("Dias Uteis")
        fora_exp=fora_and[cols_fora].copy().sort_values("Dias Uteis",ascending=False)
        rename={col_num_os:"N° OS","Dias Uteis":"Dias em Aberto"}
        if col_responsavel: rename[col_responsavel]="Responsável"
        if col_status: rename[col_status]="Status"
        pd.DataFrame([[f"Ordens de Serviço Fora do SLA (> {sla_dias} Dias Úteis)"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
        fora_exp.rename(columns=rename).to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(fora_exp)+4
        cols_geral=[col_num_os]
        if col_responsavel: cols_geral.append(col_responsavel)
        if col_empresa: cols_geral.append(col_empresa)
        if col_status: cols_geral.append(col_status)
        cols_geral.append("Dias Uteis")
        geral_exp=andamento[cols_geral].copy().sort_values("Dias Uteis",ascending=False)
        rename_g={col_num_os:"N° OS","Dias Uteis":"Dias em Aberto"}
        if col_responsavel: rename_g[col_responsavel]="Responsável"
        if col_empresa: rename_g[col_empresa]="Empresa"
        if col_status: rename_g[col_status]="Status"
        pd.DataFrame([["Ordens de Serviços em Andamento"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
        geral_exp.rename(columns=rename_g).to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(geral_exp)+4
        if len(cef_tab)>0:
            pd.DataFrame([["Ordens de Serviço — Caixa Econômica Federal (Mês a Mês)"]]).to_excel(writer,sheet_name=sheet,startrow=start,index=False,header=False); start+=1
            cef_tab.to_excel(writer,sheet_name=sheet,startrow=start,index=False); start+=len(cef_tab)+4
        ws=writer.sheets[sheet]
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value,float) and 0<cell.value<=1.0: cell.number_format="0%"
    output.seek(0); return output

# ─── PDFs ──────────────────────────────────────────────────────────────────────

def _tab_style(t, AZUL, BRANCO, CINZA, CINZA_BD, has_total=False, left_col=True):
    s=[('BACKGROUND',(0,0),(-1,0),AZUL),('TEXTCOLOR',(0,0),(-1,0),BRANCO),
       ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),
       ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
       ('ROWBACKGROUNDS',(0,1),(-1,-2 if has_total else -1),[BRANCO,CINZA]),
       ('GRID',(0,0),(-1,-1),0.3,CINZA_BD),
       ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
    if left_col: s.append(('ALIGN',(0,1),(0,-1),'LEFT'))
    if has_total:
        s+=[('BACKGROUND',(0,-1),(-1,-1),AZUL),('TEXTCOLOR',(0,-1),(-1,-1),BRANCO),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]
    t.setStyle(TableStyle(s))

def gerar_pdf_os(dados, tab_mes, resumo, nome_arq, data_arq):
    AZUL=colors.HexColor('#1F4E79'); AZUL_CLARO=colors.HexColor('#e8f0f8')
    CINZA=colors.HexColor('#f5f8fc'); CINZA_BD=colors.HexColor('#e0e0e0')
    BRANCO=colors.white; PRETO=colors.HexColor('#2c2c2a')
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=1.5*cm,rightMargin=1.5*cm,topMargin=1.5*cm,bottomMargin=1.5*cm)
    styles=getSampleStyleSheet()
    normal=ParagraphStyle('n',fontSize=8,textColor=PRETO,fontName='Helvetica')
    sec=ParagraphStyle('s',fontSize=11,textColor=AZUL,fontName='Helvetica-Bold',spaceBefore=10,spaceAfter=4)
    valor_s=ParagraphStyle('v',fontSize=15,textColor=AZUL,fontName='Helvetica-Bold',alignment=TA_CENTER)
    def br(n): return f"{n:,}".replace(",",".")
    story=[]
    ht=Table([[Paragraph('<font color="white" size="16"><b>Relatórios Onboarding — Status Atual</b></font>',styles['Normal'])]],colWidths=[doc.width])
    ht.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),AZUL),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),14)]))
    story.append(ht)
    it=Table([[Paragraph(f'<b>Planilha:</b> {nome_arq}',normal),Paragraph(f'<b>Carregada em:</b> {data_arq}',normal)]],colWidths=[doc.width*0.55,doc.width*0.45])
    it.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),AZUL_CLARO),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),10)]))
    story.append(it); story.append(Spacer(1,8))
    df=dados['df']; col_final=dados['col_final']; col_resp=dados['col_responsavel']
    col_emp=dados['col_empresa']; col_stat=dados['col_status']; col_nos=dados['col_num_os']; sla_d=dados['sla_dias']
    finalizadas=df[df['Status Calculado']=='Finalizada']; andamento=df[df['Status Calculado']!='Finalizada']
    dentro_and=andamento[andamento['Dentro SLA']]; fora_and=andamento[~andamento['Dentro SLA']]
    pct_dentro=round(len(dentro_and)/len(andamento)*100,1) if len(andamento)>0 else 0
    pct_fora=round(len(fora_and)/len(andamento)*100,1) if len(andamento)>0 else 0
    story.append(Paragraph('Resumo Geral',sec))
    w5=doc.width/5
    rg=Table([['TOTAL OS','FINALIZADAS','EM ANDAMENTO','DENTRO DO SLA','FORA DO SLA'],
        [Paragraph(f'<font color="#1F4E79" size="14"><b>{br(len(df))}</b></font>',valor_s),
         Paragraph(f'<font color="#1F4E79" size="14"><b>{br(len(finalizadas))}</b></font>',valor_s),
         Paragraph(f'<font color="#1F4E79" size="14"><b>{br(len(andamento))}</b></font>',valor_s),
         Paragraph(f'<font color="#1a7a4a" size="14"><b>{br(len(dentro_and))}</b></font>',valor_s),
         Paragraph(f'<font color="#c0392b" size="14"><b>{br(len(fora_and))}</b></font>',valor_s)],
        ['','','',f'{pct_dentro}%',f'{pct_fora}%']],colWidths=[w5]*5,rowHeights=[13,26,12])
    rg.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BRANCO),
        ('BOX',(0,0),(0,-1),0.5,CINZA_BD),('BOX',(1,0),(1,-1),0.5,CINZA_BD),('BOX',(2,0),(2,-1),0.5,CINZA_BD),('BOX',(3,0),(3,-1),0.5,CINZA_BD),('BOX',(4,0),(4,-1),0.5,CINZA_BD),
        ('FONTSIZE',(0,0),(-1,-1),7),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#888888')),('TEXTCOLOR',(0,2),(-1,2),colors.HexColor('#888888')),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(rg); story.append(Spacer(1,8))
    story.append(Paragraph('OS Finalizadas por Mês',sec))
    mes_rows=[['Mês','Finalizadas','Dentro do SLA','% Dentro do SLA','Fora do SLA','% Fora do SLA']]
    for _,row in tab_mes.iterrows():
        mes_rows.append([row['Mês'],str(int(row['Finalizadas'])),str(int(row['Dentro'])),f"{int(row['Dentro_pct'])}%",str(int(row['Fora'])),f"{int(row['Fora_pct'])}%"])
    tf=int(tab_mes['Finalizadas'].sum()); td=int(tab_mes['Dentro'].sum()); tfo=int(tab_mes['Fora'].sum())
    mes_rows.append(['Total',br(tf),br(td),f'{round(td/tf*100) if tf>0 else 0}%',br(tfo),f'{round(tfo/tf*100) if tf>0 else 0}%'])
    tm=Table(mes_rows,colWidths=[doc.width/6]*6); _tab_style(tm,AZUL,BRANCO,CINZA,CINZA_BD,has_total=True,left_col=False)
    story.append(tm); story.append(Spacer(1,8))
    if col_resp and len(andamento)>0:
        pr=andamento.groupby(col_resp).size().reset_index(name='OS em Andamento')
        pr.columns=['Responsável','OS em Andamento']; pr=pr.sort_values('OS em Andamento',ascending=False)
        rr=[['Responsável','OS em Andamento']]+[[r['Responsável'],str(r['OS em Andamento'])] for _,r in pr.iterrows()]
        rt=Table(rr,colWidths=[doc.width*0.7,doc.width*0.3]); _tab_style(rt,AZUL,BRANCO,CINZA,CINZA_BD)
        story.append(KeepTogether([Paragraph('OS em Andamento por Responsável',sec),rt])); story.append(Spacer(1,8))
    if len(fora_and)>0:
        cf=[col_nos]+([col_resp] if col_resp else [])+([col_stat] if col_stat else [])+['Dias Uteis']
        fv=fora_and[cf].copy().sort_values('Dias Uteis',ascending=False).head(20)
        rf={col_nos:'N° OS','Dias Uteis':'Dias em Aberto'}
        if col_resp: rf[col_resp]='Responsável'
        if col_stat: rf[col_stat]='Status'
        fv=fv.rename(columns=rf)
        fr=[list(fv.columns)]+[[str(v) for v in row] for _,row in fv.iterrows()]
        ft=Table(fr,colWidths=[doc.width/len(fv.columns)]*len(fv.columns)); _tab_style(ft,AZUL,BRANCO,CINZA,CINZA_BD,left_col=False)
        story.append(KeepTogether([Paragraph(f'OS Fora do SLA (> {sla_d} dias úteis)',sec),ft])); story.append(Spacer(1,8))
    if len(andamento)>0:
        cg=[col_nos]+([col_resp] if col_resp else [])+([col_emp] if col_emp else [])+([col_stat] if col_stat else [])+['Dias Uteis']
        gv=andamento[cg].copy().sort_values('Dias Uteis',ascending=False).head(30)
        rg2={col_nos:'N° OS','Dias Uteis':'Dias em Aberto'}
        if col_resp: rg2[col_resp]='Responsável'
        if col_emp: rg2[col_emp]='Empresa'
        if col_stat: rg2[col_stat]='Status'
        gv=gv.rename(columns=rg2)
        ts2=ParagraphStyle('tw',fontSize=7,fontName='Helvetica',leading=9)
        tem_emp='Empresa' in gv.columns; tem_resp='Responsável' in gv.columns
        nc=len(gv.columns); ex=sum([tem_emp,tem_resp]); cwb=doc.width/(nc+ex)
        gcw=[cwb*2 if c in ('Empresa','Responsável') else cwb for c in gv.columns]
        ie=list(gv.columns).index('Empresa') if tem_emp else -1
        ir=list(gv.columns).index('Responsável') if tem_resp else -1
        gr=[list(gv.columns)]
        for _,row in gv.iterrows():
            gr.append([Paragraph(str(row[c]),ts2) if c in ('Empresa','Responsável') else str(row[c]) for c in gv.columns])
        gt=Table(gr,colWidths=gcw)
        ts3=[('BACKGROUND',(0,0),(-1,0),AZUL),('TEXTCOLOR',(0,0),(-1,0),BRANCO),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
             ('FONTSIZE',(0,0),(-1,-1),7),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
             ('ROWBACKGROUNDS',(0,1),(-1,-1),[BRANCO,CINZA]),('GRID',(0,0),(-1,-1),0.3,CINZA_BD),
             ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
        if ie>=0: ts3.append(('ALIGN',(ie,1),(ie,-1),'LEFT'))
        if ir>=0: ts3.append(('ALIGN',(ir,1),(ir,-1),'LEFT'))
        gt.setStyle(TableStyle(ts3))
        story.append(KeepTogether([Paragraph('OS em Andamento',sec),gt])); story.append(Spacer(1,8))
    gi=[]
    if resumo:
        gi.append(Paragraph('Resumo Executivo',sec))
        taxa=resumo['taxa_conclusao']
        dt='Alta taxa de conclusão' if taxa>=90 else 'Taxa de conclusão regular' if taxa>=70 else 'Taxa de conclusão baixa'
        w4=doc.width/4
        et=Table([['OS RECEBIDAS','OS FINALIZADAS','TAXA DE CONCLUSÃO','DENTRO DO SLA'],
            [Paragraph(f'<font color="#1F4E79" size="14"><b>{br(resumo["os_recebidas"])}</b></font>',valor_s),
             Paragraph(f'<font color="#1a7a4a" size="14"><b>{br(resumo["os_finalizadas"])}</b></font>',valor_s),
             Paragraph(f'<font color="#1F4E79" size="14"><b>{resumo["taxa_conclusao"]}%</b></font>',valor_s),
             Paragraph(f'<font color="#1a7a4a" size="14"><b>{resumo["pct_dentro_sla"]}%</b></font>',valor_s)],
            ['Total no Período',f'{br(resumo["os_finalizadas"])} Concluídas de {br(resumo["os_recebidas"])}',dt,'Das OS Finalizadas']],
            colWidths=[w4]*4,rowHeights=[13,26,12])
        et.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BRANCO),
            ('BOX',(0,0),(0,-1),0.5,CINZA_BD),('BOX',(1,0),(1,-1),0.5,CINZA_BD),('BOX',(2,0),(2,-1),0.5,CINZA_BD),('BOX',(3,0),(3,-1),0.5,CINZA_BD),
            ('FONTSIZE',(0,0),(-1,-1),7),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#888888')),('TEXTCOLOR',(0,2),(-1,2),colors.HexColor('#888888')),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        gi.append(et); gi.append(Spacer(1,10))
    gi.append(Paragraph('OS Finalizadas por Mês — SLA',sec))
    mg=tab_mes['Mês'].tolist(); dg=tab_mes['Dentro_pct'].tolist(); fg=tab_mes['Fora_pct'].tolist(); qg=tab_mes['Finalizadas'].tolist()
    n=len(mg); GW=doc.width; LH=55; ES=10; BH=110; LBH=18
    d=Drawing(GW,LH+ES+BH+LBH); gap=GW/n; bw=gap*0.45; bb=LBH
    for pct in [0,25,50,75,100]:
        y=bb+BH*pct/100
        d.add(Line(28,y,GW-5,y,strokeColor=colors.HexColor('#e8edf2'),strokeWidth=0.4))
        d.add(String(24,y-3,f'{pct}%',fontSize=6,fillColor=colors.HexColor('#888888'),textAnchor='end'))
    for i,mes in enumerate(mg):
        cx=gap*i+gap/2; xb=cx-bw/2; hd=BH*dg[i]/100; hf=BH*fg[i]/100
        d.add(Rect(xb,bb,bw,hd,fillColor=colors.HexColor('#5b8dd9'),strokeColor=None))
        d.add(Rect(xb,bb+hd,bw,hf,fillColor=colors.HexColor('#e8a0a0'),strokeColor=None))
        d.add(String(cx,bb+hd/2-3,f'{dg[i]}%',fontSize=7,fillColor=colors.white,textAnchor='middle'))
        ly=bb+hd+hf/2-3 if hf>10 else bb+hd+hf+2
        d.add(String(cx,ly,f'{fg[i]}%',fontSize=6,fillColor=colors.HexColor('#8b3a3a'),textAnchor='middle'))
        d.add(String(cx,4,mes,fontSize=7,fillColor=PRETO,textAnchor='middle'))
    lb=LBH+BH+ES; qmin=min(qg)-50; qmax=max(qg)+50
    def my(v): return lb+(v-qmin)/(qmax-qmin)*(LH-20)
    pts=[(gap*i+gap/2,my(q)) for i,q in enumerate(qg)]
    for i in range(len(pts)-1): d.add(Line(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],strokeColor=colors.HexColor('#2c2c2a'),strokeWidth=1.5))
    for i,(px,py) in enumerate(pts):
        d.add(Circle(px,py,4,fillColor=colors.HexColor('#2c2c2a'),strokeColor=None))
        d.add(String(px,py+7,str(int(qg[i])),fontSize=8,fillColor=colors.HexColor('#2c2c2a'),textAnchor='middle'))
    gi.append(d); gi.append(Spacer(1,6))
    leg=Table([[Paragraph('<font color="#5b8dd9">■</font> % Dentro do SLA',normal),Paragraph('<font color="#e8a0a0">■</font> % Fora do SLA',normal),Paragraph('● Finalizadas',normal)]],colWidths=[doc.width/3]*3)
    leg.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),8)]))
    gi.append(leg); gi.append(Spacer(1,14)); story.append(KeepTogether(gi))
    story.append(HRFlowable(width='100%',thickness=0.5,color=colors.HexColor('#e0e0e0'))); story.append(Spacer(1,4))
    agora_brt=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
    rod=Table([[Paragraph('Finnet - Relatório de Onboarding - Versão 3.2',normal),
                Paragraph(f'Gerado em: {agora_brt} (horário de Brasília)',ParagraphStyle('r',fontSize=8,textColor=PRETO,fontName='Helvetica',alignment=TA_RIGHT))]],
              colWidths=[doc.width*0.6,doc.width*0.4])
    story.append(rod); doc.build(story); buf.seek(0); return buf.getvalue()

def gerar_pdf_chamados(area_label, df_area, nome_arq, data_arq):
    AZUL=colors.HexColor('#1F4E79'); AZUL_CLARO=colors.HexColor('#e8f0f8')
    CINZA=colors.HexColor('#f5f8fc'); CINZA_BD=colors.HexColor('#e0e0e0')
    BRANCO=colors.white; PRETO=colors.HexColor('#2c2c2a')
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=1.5*cm,rightMargin=1.5*cm,topMargin=1.5*cm,bottomMargin=1.5*cm)
    styles=getSampleStyleSheet()
    normal=ParagraphStyle('n',fontSize=8,textColor=PRETO,fontName='Helvetica')
    sec=ParagraphStyle('s',fontSize=11,textColor=AZUL,fontName='Helvetica-Bold',spaceBefore=10,spaceAfter=4)
    sec_sm=ParagraphStyle('ss',fontSize=9,textColor=AZUL,fontName='Helvetica-Bold',spaceBefore=8,spaceAfter=3)
    valor_s=ParagraphStyle('v',fontSize=15,textColor=AZUL,fontName='Helvetica-Bold',alignment=TA_CENTER)
    txt_wrap=ParagraphStyle('tw',fontSize=7,fontName='Helvetica',leading=9)
    tipo=df_area["Tipo"].value_counts(); total=len(df_area)
    inc=int(tipo.get("Incidente",0)); sol=int(tipo.get("Solicitação",0))
    mel=int(tipo.get("Melhoria - Solicitação de Melhoria",0)); sol_total=sol+mel
    meses=sorted(df_area["Mes"].unique()); meses_label=[mes_abrev(m) for m in meses]
    mes_atual=meses[-1]; mes_atual_lb=mes_abrev(mes_atual)
    tem_sla="Dentro do SLA" in df_area.columns; col_motivo="Motivo de abertura BU"
    if tem_sla:
        dp=int(((df_area["Dentro do SLA"]=="Dentro")|(df_area["Dentro do SLA"]=="Sem SLA")).sum())
        pct_sla=round(dp/total*100,1) if total>0 else 0
    else: pct_sla=None
    df_sol_all=df_area[df_area["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
    df_inc_all=df_area[df_area["Tipo"]=="Incidente"]
    df_mes_a=df_area[df_area["Mes"]==mes_atual]
    df_sol_mes_a=df_mes_a[df_mes_a["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
    df_inc_mes_a=df_mes_a[df_mes_a["Tipo"]=="Incidente"]
    def bloco_top3(df_f,titulo,ml,mll):
        if len(df_f)==0: return None
        top=df_f[col_motivo].value_counts().head(3).index.tolist()
        if not top: return None
        nc=2+len(ml); cw=[doc.width*0.42]+[doc.width*0.58/nc]*(nc-1)
        rows=[['Motivo']+mll+['Total']]
        for m in top:
            row=[Paragraph(str(m),txt_wrap)]; tot=0
            for mes in ml:
                q=df_f[(df_f["Mes"]==mes)&(df_f[col_motivo]==m)].shape[0]; row.append(str(q)); tot+=q
            row.append(str(tot)); rows.append(row)
        t=Table(rows,colWidths=cw); _tab_style(t,AZUL,BRANCO,CINZA,CINZA_BD)
        return KeepTogether([Paragraph(titulo,sec_sm),t,Spacer(1,5)])
    CORES_G=[colors.HexColor('#2563eb'),colors.HexColor('#f59e0b'),colors.HexColor('#6b7280'),colors.HexColor('#10b981'),colors.HexColor('#ef4444')]
    def grafico_barras_pdf(df_f,titulo,ml,mll):
        if len(df_f)==0: return []
        top=df_f[col_motivo].value_counts().head(3).index.tolist()
        if not top: return []
        ng=len(ml); GW=doc.width; BH=90; LH=18; TP=20; TH=BH+LH+TP
        d=Drawing(GW,TH); gap=GW/ng; bwt=gap*0.75; bw=bwt/len(top)
        av=[]; sd=[]
        for motivo in top:
            vals=[df_f[(df_f["Mes"]==mes)&(df_f[col_motivo]==motivo)].shape[0] for mes in ml]
            sd.append(vals); av.extend(vals)
        vm=max(av) if av else 1
        for frac in [0.25,0.5,0.75,1.0]:
            y=LH+BH*frac; d.add(Line(0,y,GW,y,strokeColor=colors.HexColor('#e8edf2'),strokeWidth=0.4))
        for gi2,(mes,lbl) in enumerate(zip(ml,mll)):
            cx=gap*gi2+gap/2; xs=cx-bwt/2
            for si,(motivo,vals) in enumerate(zip(top,sd)):
                v=vals[gi2]; xb=xs+si*bw; h=BH*(v/vm) if vm>0 else 0
                d.add(Rect(xb,LH,bw*0.88,h,fillColor=CORES_G[si%len(CORES_G)],strokeColor=None))
                if v>0: d.add(String(xb+bw*0.44,LH+h+3,str(v),fontSize=6,fillColor=PRETO,textAnchor='middle'))
            d.add(String(cx,3,lbl,fontSize=7,fillColor=PRETO,textAnchor='middle'))
        lr=[]
        for si,motivo in enumerate(top):
            lc=motivo if len(motivo)<=32 else motivo[:29]+'…'
            lr.append(Paragraph(f'■ {lc}',ParagraphStyle(f'lg{si}',fontSize=6,fontName='Helvetica',textColor=CORES_G[si%len(CORES_G)],leading=8)))
        lt=Table([lr],colWidths=[doc.width/len(lr)]*len(lr))
        lt.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        return [Paragraph(titulo,sec_sm),d,lt,Spacer(1,8)]
    story=[]
    ht=Table([[Paragraph(f'<font color="white" size="14"><b>Relatórios Onboarding — Status Atual Chamados {area_label}</b></font>',styles['Normal'])]],colWidths=[doc.width])
    ht.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),AZUL),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),14)]))
    story.append(ht)
    it=Table([[Paragraph(f'<b>Planilha:</b> {nome_arq}',normal),Paragraph(f'<b>Carregada em:</b> {data_arq}',normal)]],colWidths=[doc.width*0.55,doc.width*0.45])
    it.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),AZUL_CLARO),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),10)]))
    story.append(it); story.append(Spacer(1,10))
    story.append(Paragraph('Resumo Executivo',sec))
    w4=doc.width/4; pct_sla_str=f'{pct_sla}%' if pct_sla is not None else '—'
    cor_sla='#1a7a4a' if (pct_sla or 0)>=90 else '#d35400' if (pct_sla or 0)>=70 else '#c0392b'
    et=Table([['TOTAL DE CHAMADOS','TOTAL DE SOLICITAÇÕES','TOTAL DE INCIDENTES','DENTRO DO SLA'],
        [Paragraph(f'<font color="#1F4E79" size="14"><b>{total}</b></font>',valor_s),
         Paragraph(f'<font color="#1a7a4a" size="14"><b>{sol_total}</b></font>',valor_s),
         Paragraph(f'<font color="#c0392b" size="14"><b>{inc}</b></font>',valor_s),
         Paragraph(f'<font color="{cor_sla}" size="14"><b>{pct_sla_str}</b></font>',valor_s)],
        ['Total no Período',f'{round(sol_total/total*100,1) if total>0 else 0}% do total',
         f'{round(inc/total*100,1) if total>0 else 0}% do total',
         'Dos Chamados no Período' if pct_sla is not None else 'Sem coluna SLA']],colWidths=[w4]*4,rowHeights=[13,26,12])
    et.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BRANCO),
        ('BOX',(0,0),(0,-1),0.5,CINZA_BD),('BOX',(1,0),(1,-1),0.5,CINZA_BD),('BOX',(2,0),(2,-1),0.5,CINZA_BD),('BOX',(3,0),(3,-1),0.5,CINZA_BD),
        ('FONTSIZE',(0,0),(-1,-1),7),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#888888')),('TEXTCOLOR',(0,2),(-1,2),colors.HexColor('#888888')),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(et); story.append(Spacer(1,5))
    dt2=Table([[Paragraph('<b>Solicitação</b> → criação, consulta, alteração ou atividade operacional     <b>Incidente</b> → erro, falha ou comportamento incorreto do sistema/processo',
        ParagraphStyle('desc',fontSize=7,textColor=colors.HexColor('#555555'),fontName='Helvetica',leading=10))]],colWidths=[doc.width])
    dt2.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),CINZA),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),10)]))
    story.append(dt2); story.append(Spacer(1,8))
    story.append(Paragraph(f'Chamados — {area_label} | SLA por Mês',sec))
    if tem_sla:
        so=df_area.groupby("Mes").agg(Total=("Mes","count"),
            Dentro=("Dentro do SLA",lambda x:((x=="Dentro")|(x=="Sem SLA")).sum()),
            Fora=("Dentro do SLA",lambda x:(x=="Fora").sum())).reset_index().sort_values("Mes")
        so["pct_dentro"]=(so["Dentro"]/so["Total"]*100).round(0).astype(int)
        so["pct_fora"]=(so["Fora"]/so["Total"]*100).round(0).astype(int)
        so["Mês"]=so["Mes"].apply(mes_abrev)
        sr=[['Mês','Total','Dentro do SLA','% Dentro','Fora do SLA','% Fora']]
        for _,r in so.iterrows():
            sr.append([r['Mês'],str(int(r['Total'])),str(int(r['Dentro'])),f"{int(r['pct_dentro'])}%",str(int(r['Fora'])),f"{int(r['pct_fora'])}%"])
        td2=int(so['Dentro'].sum()); tf2=int(so['Fora'].sum()); tt2=int(so['Total'].sum())
        sr.append(['Total',str(tt2),str(td2),f"{round(td2/tt2*100) if tt2>0 else 0}%",str(tf2),f"{round(tf2/tt2*100) if tt2>0 else 0}%"])
        ts4=Table(sr,colWidths=[doc.width/6]*6); _tab_style(ts4,AZUL,BRANCO,CINZA,CINZA_BD,has_total=True,left_col=False)
        story.append(ts4)
    else:
        ss=df_area.groupby("Mes").agg(Total=("Mes","count")).reset_index()
        ss["Mês"]=ss["Mes"].apply(mes_abrev)
        rs=[['Mês','Total']]+[[r['Mês'],str(int(r['Total']))] for _,r in ss.iterrows()]
        ts5=Table(rs,colWidths=[doc.width*0.5]*2); _tab_style(ts5,AZUL,BRANCO,CINZA,CINZA_BD,left_col=False)
        story.append(ts5)
    story.append(Spacer(1,8))
    for bloco in [bloco_top3(df_sol_all,'Top 3 Motivos de Solicitações — Período Completo',meses,meses_label),
                  bloco_top3(df_sol_mes_a,f'Top 3 Motivos de Solicitações — {mes_atual_lb}',[mes_atual],[mes_atual_lb]),
                  bloco_top3(df_inc_all,'Top 3 Motivos de Incidentes — Período Completo',meses,meses_label),
                  bloco_top3(df_inc_mes_a,f'Top 3 Motivos de Incidentes — {mes_atual_lb}',[mes_atual],[mes_atual_lb])]:
        if bloco: story.append(bloco)
    if "Criado por" in df_area.columns:
        tp2=df_area["Criado por"].value_counts().head(3).index.tolist()
        if tp2:
            rp2=[['Solicitante']+meses_label+['Total']]
            for s in tp2:
                row=[Paragraph(str(s),txt_wrap)]; tot=0
                for mes in meses:
                    q=df_area[(df_area["Mes"]==mes)&(df_area["Criado por"]==s)].shape[0]; row.append(str(q)); tot+=q
                row.append(str(tot)); rp2.append(row)
            nc2=2+len(meses); cw2=[doc.width*0.42]+[doc.width*0.58/nc2]*(nc2-1)
            tp3=Table(rp2,colWidths=cw2); _tab_style(tp3,AZUL,BRANCO,CINZA,CINZA_BD)
            story.append(KeepTogether([Paragraph('Top 3 Solicitantes',sec_sm),tp3,Spacer(1,5)]))
    story.append(PageBreak())
    story.append(Paragraph('Gráficos de Chamados',sec)); story.append(Spacer(1,6))
    if tem_sla:
        story.append(Paragraph(f'Chamados {area_label} por Mês — SLA',sec_sm))
        mg2=so["Mês"].tolist(); dg2=so["pct_dentro"].tolist(); fg2=so["pct_fora"].tolist(); qg2=so["Total"].tolist()
        n2=len(mg2); GW=doc.width; LH2=50; ES2=8; BH2=100; LBH2=18
        d2=Drawing(GW,LH2+ES2+BH2+LBH2); gap2=GW/n2; bw2=gap2*0.45; bb2=LBH2
        for pct in [0,25,50,75,100]:
            y=bb2+BH2*pct/100
            d2.add(Line(28,y,GW-5,y,strokeColor=colors.HexColor('#e8edf2'),strokeWidth=0.4))
            d2.add(String(24,y-3,f'{pct}%',fontSize=6,fillColor=colors.HexColor('#888888'),textAnchor='end'))
        for i,mes in enumerate(mg2):
            cx=gap2*i+gap2/2; xb=cx-bw2/2; hd=BH2*dg2[i]/100; hf=BH2*fg2[i]/100
            d2.add(Rect(xb,bb2,bw2,hd,fillColor=colors.HexColor('#b8c8e8'),strokeColor=None))
            d2.add(Rect(xb,bb2+hd,bw2,hf,fillColor=colors.HexColor('#f5c08a'),strokeColor=None))
            d2.add(String(cx,bb2+hd/2-3,f'{dg2[i]}%',fontSize=7,fillColor=colors.HexColor('#1e3a5f'),textAnchor='middle'))
            ly=bb2+hd+hf/2-3 if hf>10 else bb2+hd+hf+2
            d2.add(String(cx,ly,f'{fg2[i]}%',fontSize=6,fillColor=colors.HexColor('#7a4a00'),textAnchor='middle'))
            d2.add(String(cx,4,mes,fontSize=7,fillColor=PRETO,textAnchor='middle'))
        lb2=LBH2+BH2+ES2; qmin2=min(qg2)-max(1,int(min(qg2)*0.1)); qmax2=max(qg2)+max(1,int(max(qg2)*0.1))
        def my2(v): return lb2+(v-qmin2)/(qmax2-qmin2)*(LH2-15)
        pts2=[(gap2*i+gap2/2,my2(q)) for i,q in enumerate(qg2)]
        for i in range(len(pts2)-1): d2.add(Line(pts2[i][0],pts2[i][1],pts2[i+1][0],pts2[i+1][1],strokeColor=colors.HexColor('#2563eb'),strokeWidth=1.5))
        for i,(px,py) in enumerate(pts2):
            d2.add(Circle(px,py,4,fillColor=colors.HexColor('#2563eb'),strokeColor=None))
            d2.add(String(px,py+7,str(int(qg2[i])),fontSize=7,fillColor=colors.HexColor('#1e3a5f'),textAnchor='middle'))
        story.append(d2)
        ls=Table([[Paragraph('<font color="#b8c8e8">■</font> % Dentro do SLA',normal),Paragraph('<font color="#f5c08a">■</font> % Fora do SLA',normal),Paragraph('● Total de Chamados',normal)]],colWidths=[doc.width/3]*3)
        ls.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),7)]))
        story.append(ls); story.append(Spacer(1,12))
    for df_f,titulo,ml,mll in [(df_sol_all,f'Top 3 Motivos de Solicitações — Período Completo',meses,meses_label),
                                (df_sol_mes_a,f'Top 3 Motivos de Solicitações — {mes_atual_lb}',[mes_atual],[mes_atual_lb]),
                                (df_inc_all,f'Top 3 Motivos de Incidentes — Período Completo',meses,meses_label),
                                (df_inc_mes_a,f'Top 3 Motivos de Incidentes — {mes_atual_lb}',[mes_atual],[mes_atual_lb])]:
        for fl in grafico_barras_pdf(df_f,titulo,ml,mll): story.append(fl)
    story.append(HRFlowable(width='100%',thickness=0.5,color=CINZA_BD)); story.append(Spacer(1,4))
    agora_brt=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
    rod=Table([[Paragraph('Finnet - Relatório de Onboarding - Versão 3.2',normal),
                Paragraph(f'Gerado em: {agora_brt} (horário de Brasília)',ParagraphStyle('r',fontSize=8,textColor=PRETO,fontName='Helvetica',alignment=TA_RIGHT))]],
              colWidths=[doc.width*0.6,doc.width*0.4])
    story.append(rod); doc.build(story); buf.seek(0); return buf.getvalue()


# ─── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📊 Relatórios Onboarding Finance")
    st.markdown("---")
    opcoes=["🏠 Início","📋 Chamados — Implantação","📋 Chamados — Tech","📋 Chamados — Produtos",
            "📊 Gráficos — Chamados","📄 Status Atual — Chamados","🔧 Ordens de Serviço",
            "📈 Gráficos — OS","📄 Status Atual — OS","👤 Desempenho Individual",
            "⚙️ Configuração de Motivos","ℹ️ Sobre"]
    pagina=st.radio("Navegação",opcoes,label_visibility="collapsed")
    st.markdown("---")
    st.markdown('<div class="footer-custom">Versão 3.2</div>', unsafe_allow_html=True)

st.markdown("""
<div class="main-header" style="display:flex;align-items:center;justify-content:space-between;">
    <div><h1>📊 Relatórios Onboarding</h1><p>Análise de Chamados e Ordens de Serviço</p></div>
    <img src="https://raw.githubusercontent.com/wellpkaraujo/OnboardingFinance/main/finnet.jpg"
         style="height:72px;mix-blend-mode:lighten;opacity:0.92;" alt="Finnet" />
</div>
""", unsafe_allow_html=True)

# ─── PÁGINAS ───────────────────────────────────────────────────────────────────

if pagina == "🏠 Início":
    st.markdown("### Bem-vindo ao sistema de Relatórios Onboarding")
    st.markdown("Utilize o menu lateral para navegar entre os módulos.")
    tem_imp=st.session_state.df_chamados_implantacao is not None
    tem_tech=st.session_state.df_chamados_tech is not None
    tem_map=st.session_state.df_chamados_produtos is not None
    tem_os=st.session_state.dados_os is not None
    def _badge(ok): return "🟢" if ok else "⚪"
    st.markdown(f"""<div style="background:#f0f4f8;border-radius:10px;padding:14px 18px;margin-bottom:1rem;font-size:0.85rem;color:#444;">
        <b>Dados carregados nesta sessão:</b><br>
        {_badge(tem_imp)} Chamados Implantação &nbsp;|&nbsp; {_badge(tem_tech)} Chamados Tech &nbsp;|&nbsp;
        {_badge(tem_map)} Chamados Produtos &nbsp;|&nbsp; {_badge(tem_os)} Ordens de Serviço
    </div>""", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    with c1: st.markdown('<div class="metric-card"><div class="label">Módulo</div><div class="value" style="font-size:1.4rem">📋</div><div class="sub">Chamados Implantação</div></div>', unsafe_allow_html=True)
    with c2: st.markdown('<div class="metric-card"><div class="label">Módulo</div><div class="value" style="font-size:1.4rem">📋</div><div class="sub">Chamados Tech</div></div>', unsafe_allow_html=True)
    with c3: st.markdown('<div class="metric-card"><div class="label">Módulo</div><div class="value" style="font-size:1.4rem">📋</div><div class="sub">Chamados Produtos</div></div>', unsafe_allow_html=True)
    with c4: st.markdown('<div class="metric-card"><div class="label">Módulo</div><div class="value" style="font-size:1.4rem">🔧</div><div class="sub">Ordens de Serviço</div></div>', unsafe_allow_html=True)

elif pagina in ["📋 Chamados — Implantação","📋 Chamados — Tech","📋 Chamados — Produtos"]:
    area=pagina.split("— ")[1]
    dic_map={"Implantação":st.session_state.dic_implantacao,"Tech":st.session_state.dic_tech,"Produtos":st.session_state.dic_produtos}
    dic=dic_map[area]
    chave_df={"Implantação":"df_chamados_implantacao","Tech":"df_chamados_tech","Produtos":"df_chamados_produtos"}
    chave_nome={"Implantação":"nome_chamados_implantacao","Tech":"nome_chamados_tech","Produtos":"nome_chamados_produtos"}
    chave_data={"Implantação":"data_chamados_implantacao","Tech":"data_chamados_tech","Produtos":"data_chamados_produtos"}
    area_key_map={"Implantação":"implantacao","Tech":"tech","Produtos":"produtos"}
    st.markdown(f'<div class="section-title">📋 Chamados — {area}</div>', unsafe_allow_html=True)
    arquivo=st.file_uploader(f"Selecione a planilha de chamados ({area})",type=["xlsx","csv"],key=f"upload_{area}")
    if arquivo:
        with st.spinner("Analisando..."):
            if arquivo.name.endswith(".csv"):
                df_raw=pd.read_csv(arquivo,encoding="utf-8-sig",sep=None,engine="python")
            else:
                df_raw=pd.read_excel(arquivo)
            df_raw.columns=df_raw.columns.str.strip()
            df_raw.columns=[c.lstrip('\ufeff') for c in df_raw.columns]
            try: df=analisar_chamados(df_raw,dic)
            except KeyError as e: st.error(f"❌ Erro: {e}"); st.stop()
            agora_brt=datetime.now(timezone(timedelta(hours=-3)))
            st.session_state[chave_df[area]]=df
            st.session_state[chave_nome[area]]=arquivo.name
            st.session_state[chave_data[area]]=agora_brt.strftime("%d/%m/%Y às %H:%M")
        with st.spinner("Salvando..."):
            pdf_bytes_ch=gerar_pdf_chamados(area,df,st.session_state[chave_nome[area]],st.session_state[chave_data[area]])
            upload_pdf_chamados_github(pdf_bytes_ch,area_key_map[area],nome_arq=st.session_state[chave_nome[area]],data_arq=st.session_state[chave_data[area]])
            salvar_estado_github(salvar_dfs=True)
            st.toast(f"✅ Chamados {area} salvos!", icon="✅")
    df=st.session_state.get(chave_df[area])
    if df is None:
        st.info(f"Selecione uma planilha de Chamados — {area} para iniciar a análise.")
    else:
        nome_arq=st.session_state.get(chave_nome[area]); data_arq=st.session_state.get(chave_data[area])
        if nome_arq and data_arq:
            st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {nome_arq} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {data_arq}</div>', unsafe_allow_html=True)
        meses=sorted(df["Mes"].unique()); meses_label=[mes_abrev(m) for m in meses]
        total=len(df); tipo=df["Tipo"].value_counts()
        inc=tipo.get("Incidente",0); sol=tipo.get("Solicitação",0); mel=tipo.get("Melhoria - Solicitação de Melhoria",0)
        st.markdown('<div class="section-title">Visão Geral</div>', unsafe_allow_html=True)
        c1,c2,c3,c4=st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="label">Total de Chamados</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card metric-red"><div class="label">Incidentes</div><div class="value">{inc}</div><div class="sub">{round(inc/total*100,1) if total>0 else 0}%</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card metric-green"><div class="label">Solicitações</div><div class="value">{sol}</div><div class="sub">{round(sol/total*100,1) if total>0 else 0}%</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card metric-orange"><div class="label">Melhorias</div><div class="value">{mel}</div><div class="sub">{round(mel/total*100,1) if total>0 else 0}%</div></div>', unsafe_allow_html=True)
        st.markdown("")
        st.markdown('<div class="section-title">SLA por Mês</div>', unsafe_allow_html=True)
        tem_sla_col="Dentro do SLA" in df.columns
        if tem_sla_col:
            sla=df.groupby("Mes").agg(Total=("Mes","count"),
                Dentro=("Dentro do SLA",lambda x:((x=="Dentro")|(x=="Sem SLA")).sum()),
                Fora=("Dentro do SLA",lambda x:(x=="Fora").sum())).reset_index()
            sla["% Dentro"]=(sla["Dentro"]/sla["Total"]*100).round(0).astype(int).astype(str)+"%"
            sla["% Fora"]=(sla["Fora"]/sla["Total"]*100).round(0).astype(int).astype(str)+"%"
            sla["Mês"]=sla["Mes"].apply(mes_abrev)
            st.markdown(estilizar(sla[["Mês","Total","Dentro","% Dentro","Fora","% Fora"]]), unsafe_allow_html=True)
        else:
            ss=df.groupby("Mes").agg(Total=("Mes","count")).reset_index()
            ss["Mês"]=ss["Mes"].apply(mes_abrev)
            st.markdown(estilizar(ss[["Mês","Total"]]), unsafe_allow_html=True)
        def tbl_top3(df_f,titulo,col_id="Motivo",col_motivo="Motivo de abertura BU"):
            if len(df_f)==0: return
            top=df_f[col_motivo].value_counts().head(3).index.tolist()
            if not top: return
            ml2=sorted(df_f["Mes"].unique()); ml2l=[mes_abrev(m) for m in ml2]; rows=[]
            for m in top:
                row={col_id:m}; tot=0
                for mes,lbl in zip(ml2,ml2l):
                    q=df_f[(df_f["Mes"]==mes)&(df_f[col_motivo]==m)].shape[0]; row[lbl]=q; tot+=q
                row["Total"]=tot; rows.append(row)
            st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)
            st.markdown(estilizar(pd.DataFrame(rows)), unsafe_allow_html=True)
        mes_atual=meses[-1]; mes_atual_lbl=mes_abrev(mes_atual)
        df_mes_atual=df[df["Mes"]==mes_atual]
        df_sol_all=df[df["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
        df_inc_all=df[df["Tipo"]=="Incidente"]
        df_sol_mes_a=df_mes_atual[df_mes_atual["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
        df_inc_mes_a=df_mes_atual[df_mes_atual["Tipo"]=="Incidente"]
        tbl_top3(df_sol_all,f"🔵 Top 3 Motivos de Solicitações — Período Completo")
        tbl_top3(df_sol_mes_a,f"🔵 Top 3 Motivos de Solicitações — {mes_atual_lbl}")
        tbl_top3(df_inc_all,f"🔴 Top 3 Motivos de Incidentes — Período Completo")
        tbl_top3(df_inc_mes_a,f"🔴 Top 3 Motivos de Incidentes — {mes_atual_lbl}")
        st.markdown('<div class="section-title">👤 Top 3 Solicitantes</div>', unsafe_allow_html=True)
        tsp=df["Criado por"].value_counts().head(3).index; rows_p=[]
        for s in tsp:
            row={"Solicitante":s}; tot=0
            for mes,lbl in zip(meses,meses_label):
                q=df[(df["Mes"]==mes)&(df["Criado por"]==s)].shape[0]; row[lbl]=q; tot+=q
            row["Total"]=tot; rows_p.append(row)
        st.markdown(estilizar(pd.DataFrame(rows_p)), unsafe_allow_html=True)
        rows_m=[]
        for s in tsp:
            temp=df[df["Criado por"]==s]; top_m=temp["Motivo de abertura BU"].value_counts().head(3)
            rows_m.append({"Solicitante":s,
                "1º Motivo":top_m.index[0] if len(top_m)>0 else "-","Qtd 1":top_m.iloc[0] if len(top_m)>0 else 0,
                "2º Motivo":top_m.index[1] if len(top_m)>1 else "-","Qtd 2":top_m.iloc[1] if len(top_m)>1 else 0,
                "3º Motivo":top_m.index[2] if len(top_m)>2 else "-","Qtd 3":top_m.iloc[2] if len(top_m)>2 else 0})
        st.markdown(estilizar(pd.DataFrame(rows_m)), unsafe_allow_html=True)
        st.markdown("")
        excel=gerar_excel_chamados(df,meses,meses_label)
        st.download_button(label="📥 Exportar Relatório Excel",data=excel,
            file_name=f"Relatorio_Chamados_{area}_{datetime.today().strftime('%d%m%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif pagina == "📊 Gráficos — Chamados":
    import streamlit.components.v1 as components
    st.markdown('<div class="section-title">📊 Gráficos — Chamados</div>', unsafe_allow_html=True)
    def render_graficos_chamados(df_area,label_area):
        import json as _json
        meses=sorted(df_area["Mes"].unique()); meses_label=[mes_abrev(m) for m in meses]; mes_atual=meses[-1]
        tipo=df_area["Tipo"].value_counts(); total=len(df_area)
        inc=int(tipo.get("Incidente",0)); sol=int(tipo.get("Solicitação",0))
        mel=int(tipo.get("Melhoria - Solicitação de Melhoria",0)); sol_total=sol+mel
        tem_sla="Dentro do SLA" in df_area.columns
        if tem_sla:
            dp=int(((df_area["Dentro do SLA"]=="Dentro")|(df_area["Dentro do SLA"]=="Sem SLA")).sum())
            pct_sla=round(dp/total*100,1) if total>0 else 0
        else: pct_sla=None

        # Média mensal de chamados
        sla_mes=df_area.groupby("Mes").size().reset_index(name="Total_Mes")
        media_mensal_ch=round(sla_mes["Total_Mes"].mean(),1) if len(sla_mes)>0 else 0
        meses_com_ch=len(sla_mes)
        sub_media_ch=f"Média em {meses_com_ch} {'mês' if meses_com_ch==1 else 'meses'}" if meses_com_ch>0 else "—"

        c1,c2,c3,c4,c5=st.columns(5)
        with c1: st.markdown(f'<div class="metric-card"><div class="label">Total de Chamados</div><div class="value">{total}</div><div class="sub">Total no Período</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card metric-green"><div class="label">Total de Solicitações</div><div class="value">{sol_total}</div><div class="sub">{round(sol_total/total*100,1) if total>0 else 0}% do total</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card metric-red"><div class="label">Total de Incidentes</div><div class="value">{inc}</div><div class="sub">{round(inc/total*100,1) if total>0 else 0}% do total</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="label">Média / Mês</div><div class="value">{media_mensal_ch}</div><div class="sub">{sub_media_ch}</div></div>', unsafe_allow_html=True)
        with c5:
            if pct_sla is not None:
                cor="metric-green" if pct_sla>=90 else "metric-orange" if pct_sla>=70 else "metric-red"
                st.markdown(f'<div class="metric-card {cor}"><div class="label">Dentro do SLA</div><div class="value">{pct_sla}%</div><div class="sub">Dos Chamados no Período</div></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="metric-card"><div class="label">Dentro do SLA</div><div class="value">—</div></div>', unsafe_allow_html=True)
        st.markdown("""<div style="background:#f8fafc;border-left:3px solid #cbd5e1;border-radius:6px;padding:8px 14px;margin:10px 0 18px;font-size:0.82rem;color:#555;">
            <b>Solicitação</b> → criação, consulta, alteração ou atividade operacional&nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Incidente</b> → erro, falha ou comportamento incorreto do sistema/processo</div>""", unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">Chamados {label_area} por Mês — SLA</div>', unsafe_allow_html=True)
        if tem_sla:
            sla=df_area.groupby("Mes").agg(Total=("Mes","count"),
                Dentro=("Dentro do SLA",lambda x:((x=="Dentro")|(x=="Sem SLA")).sum()),
                Fora=("Dentro do SLA",lambda x:(x=="Fora").sum())).reset_index()
        else:
            sla=df_area.groupby("Mes").agg(Total=("Mes","count")).reset_index()
            sla["Dentro"]=sla["Total"]; sla["Fora"]=0
        sla["pct_dentro"]=(sla["Dentro"]/sla["Total"]*100).round(0).astype(int)
        sla["pct_fora"]=(sla["Fora"]/sla["Total"]*100).round(0).astype(int)
        sla["label"]=sla["Mes"].apply(mes_abrev)
        labels=sla["label"].tolist(); qtd=sla["Total"].tolist()
        dentro=sla["pct_dentro"].tolist(); fora=sla["pct_fora"].tolist()
        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#b8c8e8;display:inline-block;"></span> % Dentro do SLA</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#f5c08a;display:inline-block;"></span> % Fora do SLA</span>
    <span><span style="width:20px;height:2px;background:#2563eb;display:inline-block;vertical-align:middle;"></span> Total de Chamados</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="lineChart"></canvas></div>
  <div style="position:relative;width:100%;height:260px;"><canvas id="barChart"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={_json.dumps(labels)},qtd={qtd},dentro={dentro},fora={fora};
let barChart,lineChart;
barChart=new Chart(document.getElementById('barChart').getContext('2d'),{{data:{{labels,datasets:[
  {{type:'bar',label:'% Dentro do SLA',data:dentro,backgroundColor:'#b8c8e8',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}},
  {{type:'bar',label:'% Fora do SLA',data:fora,backgroundColor:'#f5c08a',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}}
]}},options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLine}},
layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}}}},
scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:12}},color:'#888780'}},border:{{display:false}}}},
y:{{stacked:true,min:0,max:100,ticks:{{callback:v=>v+'%',font:{{size:11}},color:'#888780',stepSize:25}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}}}}},
plugins:[{{id:'barLabels',afterDatasetsDraw(chart){{
  const ctx2=chart.ctx;
  [[0,dentro,'#1e3a5f'],[1,fora,'#7a4a00']].forEach(([di,vals,clr])=>{{
    chart.getDatasetMeta(di).data.forEach((bar,i)=>{{if(!vals[i])return;
      ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle=clr;
      ctx2.textAlign='center';ctx2.textBaseline='middle';
      ctx2.fillText(vals[i]+'%',bar.x,bar.y+bar.height/2);ctx2.restore();}});
  }});}}}}]
}});
function syncLine(){{
  if(!barChart)return;
  const meta=barChart.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barChart.width-xPos[xPos.length-1];
  if(lineChart)lineChart.destroy();
  lineChart=new Chart(document.getElementById('lineChart').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:qtd,borderColor:'#2563eb',backgroundColor:'#2563eb',
    pointBackgroundColor:'#2563eb',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},
    plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:Math.min(...qtd)*0.85,max:Math.max(...qtd)*1.1}}}}}},
    plugins:[{{id:'lineLabels',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;
      chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 12px Inter,sans-serif';ctx2.fillStyle='#1e3a5f';
        ctx2.textAlign='center';ctx2.fillText(qtd[i],pt.x,pt.y-10);ctx2.restore();}});}}}}]
  }});
}}
</script></body></html>""", height=380)
        def grafico_motivos_mes(df_f,titulo,top_n=3,col_motivo="Motivo de abertura BU"):
            if len(df_f)==0: st.info(f"Sem dados para: {titulo}"); return
            top_motivos=df_f[col_motivo].value_counts().head(top_n).index.tolist()
            if not top_motivos: return
            ml2=sorted(df_f["Mes"].unique()); ml2l=[mes_abrev(m) for m in ml2]
            totais=[]; datasets=[]; CORES=["#2563eb","#f59e0b","#6b7280","#10b981","#ef4444"]
            for idx,motivo in enumerate(top_motivos):
                vals=[df_f[(df_f["Mes"]==m)&(df_f[col_motivo]==motivo)].shape[0] for m in ml2]
                totais.append(int(df_f[df_f[col_motivo]==motivo].shape[0]))
                datasets.append({"label":motivo,"data":vals,"backgroundColor":CORES[idx%len(CORES)],"borderRadius":3,"barPercentage":0.7,"categoryPercentage":0.8})
            st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)
            cid=f"chart_{abs(hash(titulo+label_area))}"
            ds_js=_json.dumps(datasets); lbl_js=_json.dumps(ml2l)
            components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="position:relative;width:100%;height:320px;"><canvas id="{cid}"></canvas></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('{cid}').getContext('2d'),{{
  type:'bar',data:{{labels:{lbl_js},datasets:{ds_js}}},
  options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:28,bottom:4}}}},
    plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}},padding:16,boxWidth:12}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:12}},color:'#555'}},border:{{display:false}}}},
    y:{{beginAtZero:true,grid:{{color:'rgba(0,0,0,0.06)'}},ticks:{{precision:0,font:{{size:11}},color:'#777'}},border:{{display:false}}}}}}}},
  plugins:[{{id:'topLabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,dIdx)=>{{
      chart.getDatasetMeta(dIdx).data.forEach((bar,i)=>{{
        const v=chart.data.datasets[dIdx].data[i];if(v===0)return;
        ctx2.save();ctx2.font='bold 11px Inter,sans-serif';ctx2.fillStyle='#333';
        ctx2.textAlign='center';ctx2.textBaseline='bottom';ctx2.fillText(v,bar.x,bar.y-3);ctx2.restore();
      }});
    }});}}}}]
}});
</script></body></html>""", height=360)
            cols=st.columns(min(top_n,len(top_motivos)))
            for i,(motivo,tot) in enumerate(zip(top_motivos,totais)):
                with cols[i]:
                    lbl=motivo if len(motivo)<=28 else motivo[:25]+"…"
                    st.markdown(f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 10px;text-align:center;"><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:6px;">{lbl}</div><div style="font-size:1.7rem;font-weight:800;color:#1F4E79;">{tot}</div></div>', unsafe_allow_html=True)
        df_sol_all=df_area[df_area["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
        df_inc_all=df_area[df_area["Tipo"]=="Incidente"]
        df_mes_atual2=df_area[df_area["Mes"]==mes_atual]
        df_sol_ma=df_mes_atual2[df_mes_atual2["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])]
        df_inc_ma=df_mes_atual2[df_mes_atual2["Tipo"]=="Incidente"]
        mal=mes_abrev(mes_atual)
        grafico_motivos_mes(df_sol_all,f"Top 3 Motivos de Solicitações — Período Completo")
        grafico_motivos_mes(df_inc_all,f"Top 3 Motivos de Incidentes — Período Completo")
        grafico_motivos_mes(df_sol_ma,f"Top 3 Motivos de Solicitações — {mal}")
        grafico_motivos_mes(df_inc_ma,f"Top 3 Motivos de Incidentes — {mal}")

        # ── Fluxo Diário Operacional de Chamados ──────────────────────
        try:
            if "Criação do Ticket" in df_area.columns:
                df_fluxo_ch = df_area.copy()
                df_fluxo_ch["Criação do Ticket"] = pd.to_datetime(df_fluxo_ch["Criação do Ticket"], errors="coerce", dayfirst=True)
                data_ini_ch = df_fluxo_ch["Criação do Ticket"].min().normalize()
                data_fim_ch = pd.Timestamp.today().normalize()
                dias_ch = pd.date_range(data_ini_ch, data_fim_ch, freq="D")

                ent_ch_l, labels_ch = [], []
                for dia in dias_ch:
                    ent = df_fluxo_ch[df_fluxo_ch["Criação do Ticket"].dt.normalize()==dia].shape[0]
                    ent_ch_l.append(int(ent))
                    labels_ch.append(dia.strftime("%d/%m"))

                st.markdown('<div class="section-title">Fluxo Diário de Abertura de Chamados</div>', unsafe_allow_html=True)
                col_fd1, col_fd2 = st.columns(2)
                with col_fd1:
                    fd_inicio = st.date_input("Data Inicial", value=data_ini_ch.date(), format="DD/MM/YYYY", key=f"fluxo_ch_{label_area}_ini")
                with col_fd2:
                    fd_fim = st.date_input("Data Final", value=data_fim_ch.date(), format="DD/MM/YYYY", key=f"fluxo_ch_{label_area}_fim")

                df_fd = pd.DataFrame({"Data": pd.to_datetime(labels_ch, format="%d/%m").map(lambda x: x.replace(year=pd.Timestamp.today().year)), "Entrantes": ent_ch_l})
                df_fd = df_fd[(df_fd["Data"].dt.date >= fd_inicio) & (df_fd["Data"].dt.date <= fd_fim)]
                labels_fd = df_fd["Data"].dt.strftime("%d/%m").tolist()
                ent_fd = df_fd["Entrantes"].tolist()

                components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> Chamados Abertos no Dia</span>
  </div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="fluxoDiarioCh_{label_area}"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_fd};
const ent={ent_fd};
new Chart(document.getElementById('fluxoDiarioCh_{label_area}').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'Chamados Abertos',data:ent,backgroundColor:'#5b8dd9',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` Abertos: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'lblFluxoCh',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.getDatasetMeta(0).data.forEach((bar,i)=>{{
      if(ent[i]===0)return;
      ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#fff';
      ctx2.textAlign='center';ctx2.textBaseline='middle';
      ctx2.fillText(ent[i],bar.x,bar.y+bar.height/2);ctx2.restore();
    }});
  }}}}]
}});
</script></body></html>""", height=340)
        except Exception as e_fd:
            st.warning(f"Erro ao gerar fluxo diário de chamados: {e_fd}")

        # ── Performance por Responsável — Chamados ────────────────────
        try:
            # Busca dinâmica pela coluna de responsável atual da planilha
            _kws_resp = ["atribuído","atribuido","responsável","responsavel","agente","assignee","assigned to","owner","analista"]
            col_resp_ch = next(
                (c for c in df_area.columns if any(kw in str(c).lower() for kw in _kws_resp)),
                None
            )
            if col_resp_ch and "Criação do Ticket" in df_area.columns:
                df_rch = df_area.copy()
                df_rch["Criação do Ticket"] = pd.to_datetime(df_rch["Criação do Ticket"], errors="coerce", dayfirst=True)
                df_rch = df_rch[df_rch[col_resp_ch].astype(str).str.strip().str.lower() != "nan"]

                st.markdown(f'<div class="section-title">Performance por Responsável — Chamados <span style="font-size:0.78rem;font-weight:400;color:#888;margin-left:8px;">coluna: {col_resp_ch}</span></div>', unsafe_allow_html=True)

                data_min_rch = df_rch["Criação do Ticket"].min().date()
                data_max_rch = pd.Timestamp.today().date()

                col_rf1, col_rf2, col_rf3 = st.columns([1,1,2])
                with col_rf1:
                    rch_ini = st.date_input("Data Inicial", value=data_min_rch, format="DD/MM/YYYY", key=f"perf_ch_{label_area}_ini")
                with col_rf2:
                    rch_fim = st.date_input("Data Final", value=data_max_rch, format="DD/MM/YYYY", key=f"perf_ch_{label_area}_fim")

                lista_resp_ch = sorted(df_rch[col_resp_ch].dropna().astype(str).str.strip().unique().tolist())
                with col_rf3:
                    resp_ch_sel = st.multiselect("Responsável(is)", options=lista_resp_ch, default=[], placeholder="Todos os responsáveis", key=f"perf_ch_{label_area}_sel")

                # Filtro de período
                df_rch_p = df_rch[(df_rch["Criação do Ticket"].dt.date >= rch_ini) & (df_rch["Criação do Ticket"].dt.date <= rch_fim)].copy()
                if resp_ch_sel:
                    df_rch_p = df_rch_p[df_rch_p[col_resp_ch].astype(str).str.strip().isin(resp_ch_sel)]

                if len(df_rch_p) == 0:
                    st.info("Nenhum chamado encontrado para os filtros selecionados.")
                else:
                    # Gráfico geral: total de chamados por responsável
                    tot_resp = df_rch_p.groupby(col_resp_ch).size().reset_index(name="Total")
                    if tem_sla:
                        inc_resp = df_rch_p[df_rch_p["Tipo"]=="Incidente"].groupby(col_resp_ch).size().reset_index(name="Incidentes")
                        sol_resp = df_rch_p[df_rch_p["Tipo"].isin(["Solicitação","Melhoria - Solicitação de Melhoria"])].groupby(col_resp_ch).size().reset_index(name="Solicitações")
                        perf_ch = tot_resp.merge(inc_resp, on=col_resp_ch, how="left").merge(sol_resp, on=col_resp_ch, how="left").fillna(0)
                        perf_ch["Incidentes"] = perf_ch["Incidentes"].astype(int)
                        perf_ch["Solicitações"] = perf_ch["Solicitações"].astype(int)
                    else:
                        perf_ch = tot_resp.copy()
                        perf_ch["Incidentes"] = 0
                        perf_ch["Solicitações"] = perf_ch["Total"]
                    perf_ch["Pct Inc (%)"] = (perf_ch["Incidentes"] / perf_ch["Total"] * 100).round(1)
                    perf_ch = perf_ch.sort_values("Total", ascending=False).head(20)

                    resp_ch_list   = perf_ch[col_resp_ch].tolist()
                    inc_ch_list    = perf_ch["Incidentes"].tolist()
                    sol_ch_list    = perf_ch["Solicitações"].tolist()
                    pct_inc_list   = perf_ch["Pct Inc (%)"].tolist()

                    components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> Solicitações</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Incidentes</span>
    <span><span style="width:20px;height:2px;background:#444;display:inline-block;vertical-align:middle;"></span> % Incidentes</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="lineChResp_{label_area}"></canvas></div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="barChResp_{label_area}"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={_json.dumps(resp_ch_list)};
const sol={sol_ch_list};const inc={inc_ch_list};const pctinc={pct_inc_list};
let barChResp,lineChResp;
barChResp=new Chart(document.getElementById('barChResp_{label_area}').getContext('2d'),{{
  data:{{labels,datasets:[
    {{type:'bar',label:'Solicitações',data:sol,backgroundColor:'#5b8dd9',stack:'rch',barPercentage:0.5,categoryPercentage:0.65}},
    {{type:'bar',label:'Incidentes',data:inc,backgroundColor:'#e8a0a0',stack:'rch',barPercentage:0.5,categoryPercentage:0.65}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLineChResp}},
    layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{stacked:true,beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'barRchLabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.getDatasetMeta(0).data.forEach((bar,i)=>{{if(sol[i]===0)return;ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(sol[i],bar.x,bar.y+bar.height/2);ctx2.restore();}});
    chart.getDatasetMeta(1).data.forEach((bar,i)=>{{if(inc[i]===0)return;ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(inc[i],bar.x,bar.y+bar.height/2);ctx2.restore();}});
  }}}}]
}});
function syncLineChResp(){{
  if(!barChResp)return;
  const meta=barChResp.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barChResp.width-xPos[xPos.length-1];
  if(lineChResp)lineChResp.destroy();
  lineChResp=new Chart(document.getElementById('lineChResp_{label_area}').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:pctinc,borderColor:'#444441',backgroundColor:'#444441',pointBackgroundColor:'#444441',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:0,max:110}}}}}},
    plugins:[{{id:'lineRchLabels',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#2c2c2a';ctx2.textAlign='center';ctx2.fillText(pctinc[i]+'%',pt.x,pt.y-10);ctx2.restore();}});
    }}}}]
  }});
}}
</script></body></html>""", height=420)

                    # Gráfico diário por responsável selecionado
                    if resp_ch_sel:
                        for nome_rch in resp_ch_sel:
                            df_um_ch = df_rch_p[df_rch_p[col_resp_ch].astype(str).str.strip()==nome_rch].copy()
                            if len(df_um_ch)==0: continue
                            dias_rch = pd.date_range(rch_ini, rch_fim, freq="D")
                            labels_dch, total_dch, inc_dch = [], [], []
                            for dia in dias_rch:
                                t = df_um_ch[df_um_ch["Criação do Ticket"].dt.normalize()==dia].shape[0]
                                i2 = df_um_ch[(df_um_ch["Criação do Ticket"].dt.normalize()==dia) & (df_um_ch["Tipo"]=="Incidente")].shape[0]
                                labels_dch.append(dia.strftime("%d/%m"))
                                total_dch.append(int(t))
                                inc_dch.append(int(i2))

                            # Remove dias zerados das bordas
                            df_dch = pd.DataFrame({"label":labels_dch,"total":total_dch,"inc":inc_dch})
                            primeiro_dch = df_dch[df_dch["total"]>0].index.min()
                            if pd.notna(primeiro_dch):
                                df_dch = df_dch.loc[primeiro_dch:]
                            labels_dch = df_dch["label"].tolist()
                            total_dch  = df_dch["total"].tolist()
                            inc_dch    = df_dch["inc"].tolist()
                            sol_dch    = [t-i for t,i in zip(total_dch,inc_dch)]

                            st.markdown(f'<div class="section-title">📅 Atividade Diária — {nome_rch}</div>', unsafe_allow_html=True)
                            cid_dch = f"diarioCh_{label_area}_{nome_rch.replace(' ','_').replace('/','_')}"
                            components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> Solicitações no Dia</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Incidentes no Dia</span>
  </div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="{cid_dch}"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_dch};const sol={sol_dch};const inc={inc_dch};
new Chart(document.getElementById('{cid_dch}').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'Solicitações',data:sol,backgroundColor:'#5b8dd9',stack:'d',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Incidentes',data:inc,backgroundColor:'#e8a0a0',stack:'d',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{stacked:true,beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'lblDch',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,di)=>{{
      chart.getDatasetMeta(di).data.forEach((bar,i)=>{{
        const val=chart.data.datasets[di].data[i];if(val===0)return;
        ctx2.save();ctx2.font='600 10px Inter,sans-serif';
        ctx2.fillStyle=di===0?'#fff':'#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';
        ctx2.fillText(val,bar.x,bar.y+bar.height/2);ctx2.restore();
      }});
    }});
  }}}}]
}});
</script></body></html>""", height=340)
        except Exception as e_rch:
            st.warning(f"Erro ao gerar gráfico de performance por responsável (chamados): {e_rch}")
    tab_imp,tab_tech,tab_prod=st.tabs(["🏗️ Chamados Implantação","🌐 Chamados Tech","🗺️ Chamados Produtos"])
    with tab_imp:
        df_imp=st.session_state.get("df_chamados_implantacao")
        if df_imp is None: st.info("📋 Carregue uma planilha em **Chamados — Implantação** para gerar os gráficos.")
        else:
            n2=st.session_state.get("nome_chamados_implantacao"); d2=st.session_state.get("data_chamados_implantacao")
            if n2 and d2: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {n2} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {d2}</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Resumo Executivo</div>', unsafe_allow_html=True)
            render_graficos_chamados(df_imp,"Implantação")
    with tab_tech:
        df_tech=st.session_state.get("df_chamados_tech")
        if df_tech is None: st.info("📋 Carregue uma planilha em **Chamados — Tech** para gerar os gráficos.")
        else:
            n2=st.session_state.get("nome_chamados_tech"); d2=st.session_state.get("data_chamados_tech")
            if n2 and d2: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {n2} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {d2}</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Resumo Executivo</div>', unsafe_allow_html=True)
            render_graficos_chamados(df_tech,"Tech")
    with tab_prod:
        df_prod=st.session_state.get("df_chamados_produtos")
        if df_prod is None: st.info("📋 Carregue uma planilha em **Chamados — Produtos** para gerar os gráficos.")
        else:
            n2=st.session_state.get("nome_chamados_produtos"); d2=st.session_state.get("data_chamados_produtos")
            if n2 and d2: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {n2} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {d2}</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Resumo Executivo</div>', unsafe_allow_html=True)
            render_graficos_chamados(df_prod,"Produtos")

elif pagina == "📄 Status Atual — Chamados":
    st.markdown('<div class="section-title">📄 Status Atual — Chamados</div>', unsafe_allow_html=True)
    def render_download_chamados(area_key,area_label):
        na=st.session_state.get(f"nome_chamados_{area_key}"); da=st.session_state.get(f"data_chamados_{area_key}")
        if na and da: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {na} &nbsp;|&nbsp; 🕐 <b>Última atualização:</b> {da}</div>', unsafe_allow_html=True)
        else: st.info(f"Carregue uma planilha em **📋 Chamados — {area_label}** para gerar o Status Atual.")
        with st.spinner("Buscando PDF..."):
            pdf_content,erro=baixar_pdf_chamados_github(area_key)
        if pdf_content: st.download_button(label=f"📥 Baixar Status Atual — Chamados {area_label} (PDF)",data=pdf_content,file_name=f"Status_Atual_Chamados_{area_label}.pdf",mime="application/pdf")
        elif erro: st.info(erro)
    tab_imp,tab_tech,tab_prod=st.tabs(["🏗️ Implantação","🌐 Tech","🗺️ Produtos"])
    with tab_imp: render_download_chamados("implantacao","Implantação")
    with tab_tech: render_download_chamados("tech","Tech")
    with tab_prod: render_download_chamados("produtos","Produtos")

elif pagina == "🔧 Ordens de Serviço":
    st.markdown('<div class="section-title">🔧 Ordens de Serviço</div>', unsafe_allow_html=True)
    sla_dias=st.number_input("SLA (dias úteis)",min_value=1,max_value=30,value=st.session_state.sla_dias,key="sla_input")
    st.session_state.sla_dias=sla_dias
    col_btn1,_=st.columns([1,4])
    with col_btn1:
        if st.button("📂 Histórico 2025"):
            with st.spinner("Carregando base histórica..."):
                bytes_hist,erro_hist=baixar_base_historica_github()
                if erro_hist: st.error(f"Erro: {erro_hist}")
                else:
                    df_hist=pd.read_excel(io.BytesIO(bytes_hist))
                    df_hist=df_hist.loc[:,~df_hist.columns.str.contains("^Unnamed")]; df_hist.columns=df_hist.columns.str.strip()
                    col_os_h=df_hist.columns[1]; df_hist=df_hist.drop_duplicates(subset=[col_os_h])
                    def find_h(kw): return next((c for c in df_hist.columns if kw in str(c).lower()),None)
                    col_fin_h=find_h("final"); col_cria_h=find_h("cria"); col_stat_h=find_h("status")
                    col_nos_h=next((c for c in df_hist.columns if any(x in str(c).lower() for x in ["n° os","n°os","numero","n. os"])),df_hist.columns[1])
                    col_resp_h=find_h("respons"); col_emp_h=find_h("empres")
                    df_hist[col_cria_h]=pd.to_datetime(df_hist[col_cria_h],dayfirst=True,errors="coerce")
                    df_hist[col_fin_h]=pd.to_datetime(df_hist[col_fin_h],dayfirst=True,errors="coerce")
                    df_hist=df_hist[df_hist[col_fin_h].dt.year==2025].copy()
                    df_hist["Dias Uteis"]=df_hist.apply(lambda r:int(np.busday_count(r[col_cria_h].date(),(r[col_fin_h]+pd.Timedelta(days=1)).date())) if not pd.isna(r[col_cria_h]) and not pd.isna(r[col_fin_h]) else 0,axis=1)
                    df_hist["Dentro SLA"]=df_hist["Dias Uteis"]<=sla_dias
                    df_hist["Status Calculado"]=df_hist[col_stat_h].apply(lambda x:"Finalizada" if str(x).strip()=="Finalizada" else "Em andamento")
                    st.session_state.dados_os={"df":df_hist,"col_status":col_stat_h,"col_responsavel":col_resp_h,"col_empresa":col_emp_h,"col_final":col_fin_h,"col_num_os":col_nos_h,"sla_dias":sla_dias}
                    st.session_state.nome_arquivo_os="Base Histórica — Jan/25 a Dez/25"
                    st.session_state.data_upload_os=datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
                    st.session_state.historico_2025_ativo=True
                    salvar_estado_github(salvar_dfs=True); st.rerun()
    arquivo_os=st.file_uploader("Selecione a planilha de OS",type=["xlsx"],key="upload_os")
    if arquivo_os:
        with st.spinner("Analisando OS..."):
            bytes_os=arquivo_os.getvalue(); df,erro=analisar_os(bytes_os,sla_dias)
            st.session_state.nome_arquivo_os=arquivo_os.name
            st.session_state.data_upload_os=datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
        if erro:
            st.error(f"ERRO ANALISAR_OS: {erro}")
            st.error(erro)
        else:
            def find(kw): return next((c for c in df.columns if kw in str(c).lower()),None)
            col_status=next((c for c in df.columns if "status" in str(c).lower() and c not in ["Status Calculado"]),None)
            col_responsavel=find("respons"); col_empresa=find("empres"); col_final=find("final")
            col_num_os=next((c for c in df.columns if any(x in str(c).lower() for x in ["n° os","n°os","numero","n. os"])),df.columns[1] if len(df.columns)>1 else None)
            finalizadas=df[df["Status Calculado"]=="Finalizada"]
            total_fin=len(finalizadas); dentro_fin=finalizadas[finalizadas["Dentro SLA"]].shape[0]
            st.session_state.resumo_executivo={"os_recebidas":len(df),"os_finalizadas":total_fin,
                "taxa_conclusao":round(total_fin/len(df)*100) if len(df)>0 else 0,
                "pct_dentro_sla":round(dentro_fin/total_fin*100) if total_fin>0 else 0}
            st.session_state.dados_os={"df":df,"col_status":col_status,"col_responsavel":col_responsavel,"col_empresa":col_empresa,"col_final":col_final,"col_num_os":col_num_os,"sla_dias":sla_dias}
            salvar_estado_github()
            st.success("FUNCAO CHAMADA")
    dados=st.session_state.get("dados_os")
    if dados is None: st.info("Selecione uma planilha de OS para iniciar a análise.")
    else:
        df=dados["df"]; col_status=dados["col_status"]; col_responsavel=dados["col_responsavel"]
        col_empresa=dados["col_empresa"]; col_final=dados["col_final"]; col_num_os=dados["col_num_os"]; sla_dias_render=dados["sla_dias"]
        finalizadas=df[df["Status Calculado"]=="Finalizada"]; andamento=df[df["Status Calculado"]!="Finalizada"]
        dentro_and=andamento[andamento["Dentro SLA"]]; fora_and=andamento[~andamento["Dentro SLA"]]
        nome_arq=st.session_state.get("nome_arquivo_os"); data_arq=st.session_state.get("data_upload_os")
        if nome_arq and data_arq: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {nome_arq} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {data_arq}</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Resumo Geral</div>', unsafe_allow_html=True)
        pct_dentro=round(len(dentro_and)/len(andamento)*100,1) if len(andamento)>0 else 0
        pct_fora=round(len(fora_and)/len(andamento)*100,1) if len(andamento)>0 else 0
        c1,c2,c3,c4,c5=st.columns(5)
        with c1: st.markdown(f'<div class="metric-card"><div class="label">Total OS</div><div class="value">{len(df)}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card metric-green"><div class="label">Finalizadas</div><div class="value">{len(finalizadas)}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="label">Em Andamento</div><div class="value">{len(andamento)}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card metric-green"><div class="label">Dentro do SLA</div><div class="value">{len(dentro_and)}</div><div class="sub">{pct_dentro}%</div></div>', unsafe_allow_html=True)
        with c5: st.markdown(f'<div class="metric-card metric-red"><div class="label">Fora do SLA</div><div class="value">{len(fora_and)}</div><div class="sub">{pct_fora}%</div></div>', unsafe_allow_html=True)
        st.markdown("")
        if col_final and len(finalizadas)>0:
            st.markdown('<div class="section-title">OS Finalizadas por Mês</div>', unsafe_allow_html=True)
            fin=finalizadas.copy(); fin["Mes"]=fin[col_final].dt.to_period("M")
            tab_mes=fin.groupby("Mes").agg(Finalizadas=("Mes","count"),Dentro=("Dentro SLA","sum")).reset_index()
            tab_mes["Fora"]=tab_mes["Finalizadas"]-tab_mes["Dentro"]
            tab_mes["Dentro_pct"]=(tab_mes["Dentro"]/tab_mes["Finalizadas"]*100).round(0).astype(int)
            tab_mes["Fora_pct"]=(tab_mes["Fora"]/tab_mes["Finalizadas"]*100).round(0).astype(int)
            tab_mes["Mês"]=tab_mes["Mes"].apply(lambda m:mes_abrev(str(m)))
            # Recebidas por mês e saldo — usa o nome real da coluna de criação
            _dados_os=st.session_state.dados_os
            df_full=_dados_os["df"].copy()
            _col_cria=_dados_os.get("col_criacao") or next(
                (col for col in df_full.columns if any(kw in str(col).lower() for kw in ["cria","abertura","created"])), None
            )
            if _col_cria and _col_cria in df_full.columns:
                df_full["_Mes_Rec"]=pd.to_datetime(df_full[_col_cria],dayfirst=True,errors="coerce").dt.to_period("M")
                rec_mes=df_full.groupby("_Mes_Rec").size().reset_index(name="Recebidas")
                rec_mes["Mes_str"]=rec_mes["_Mes_Rec"].astype(str)
                tab_mes["Mes_str"]=tab_mes["Mes"].astype(str)
                tab_mes=tab_mes.merge(rec_mes[["Mes_str","Recebidas"]],on="Mes_str",how="left")
                tab_mes["Recebidas"]=tab_mes["Recebidas"].fillna(0).astype(int)
                tab_mes["Saldo"]=tab_mes["Recebidas"]-tab_mes["Finalizadas"]
                tab_mes=tab_mes.drop(columns=["Mes_str"],errors="ignore")
            else:
                tab_mes["Recebidas"]=tab_mes["Finalizadas"]
                tab_mes["Saldo"]=0
            st.session_state.tab_mes_graficos=tab_mes
            st.markdown(estilizar_tab_mes(tab_mes), unsafe_allow_html=True)
            with st.spinner("Salvando..."):
                pdf_bytes=gerar_pdf_os(st.session_state.dados_os,tab_mes,st.session_state.get("resumo_executivo"),st.session_state.get("nome_arquivo_os",""),st.session_state.get("data_upload_os",""))
                upload_pdf_github(pdf_bytes,nome_arq=st.session_state.get("nome_arquivo_os",""),data_arq=st.session_state.get("data_upload_os",""))
                salvar_estado_github(salvar_dfs=True)
                st.toast("✅ OS salva! Dados persistidos.", icon="✅")
        if col_responsavel and len(andamento)>0:
            st.markdown('<div class="section-title">OS em Andamento por Responsável</div>', unsafe_allow_html=True)
            pr=andamento.groupby(col_responsavel).size().reset_index(name="OS em Andamento")
            pr.columns=["Responsável","OS em Andamento"]; pr=pr.sort_values("OS em Andamento",ascending=False).reset_index(drop=True)
            st.markdown(estilizar(pr), unsafe_allow_html=True)
        if len(fora_and)>0:
            st.markdown(f'<div class="section-title">🔴 OS Fora do SLA (> {sla_dias_render} dias úteis)</div>', unsafe_allow_html=True)
            cf=[col_num_os]+([col_responsavel] if col_responsavel else [])+([col_status] if col_status else [])+["Dias Uteis"]
            fv=fora_and[cf].copy().sort_values("Dias Uteis",ascending=False)
            rf={col_num_os:"N° OS","Dias Uteis":"Dias em Aberto"}
            if col_responsavel: rf[col_responsavel]="Responsável"
            if col_status: rf[col_status]="Status"
            st.markdown(estilizar(fv.rename(columns=rf)), unsafe_allow_html=True)
        if len(andamento)>0:
            st.markdown('<div class="section-title">OS em Andamento</div>', unsafe_allow_html=True)
            cg=[col_num_os]+([col_responsavel] if col_responsavel else [])+([col_empresa] if col_empresa else [])+([col_status] if col_status else [])+["Dias Uteis"]
            gv=andamento[cg].copy().sort_values("Dias Uteis",ascending=False)
            rg={col_num_os:"N° OS","Dias Uteis":"Dias em Aberto"}
            if col_responsavel: rg[col_responsavel]="Responsável"
            if col_empresa: rg[col_empresa]="Empresa"
            if col_status: rg[col_status]="Status"
            st.markdown(estilizar(gv.rename(columns=rg)), unsafe_allow_html=True)
        col_banco=next((c for c in df.columns if "banco" in str(c).lower()),None)
        if col_banco:
            cef=df[df[col_banco].astype(str).str.upper().str.strip()=="CAIXA ECONOMICA FEDERAL"].copy()
            col_cria_os=next((c for c in df.columns if "cria" in str(c).lower()),None)
            if len(cef)>0 and col_cria_os:
                st.markdown('<div class="section-title">🏦 Caixa Econômica Federal — Mês a Mês</div>', unsafe_allow_html=True)
                cef["Mes_Criacao"]=pd.to_datetime(cef[col_cria_os],dayfirst=True,errors="coerce").dt.to_period("M")
                ct=cef.groupby("Mes_Criacao").agg(Total=("Mes_Criacao","count"),Media_Dias=("Dias Uteis","mean")).reset_index().sort_values("Mes_Criacao")
                ct["Mês"]=ct["Mes_Criacao"].apply(lambda m:mes_abrev(str(m)))
                ct["Média de Dias de Conclusão"]=ct["Media_Dias"].round(0).astype(int)
                ct=ct.rename(columns={"Total":"Total OS"})
                st.markdown(estilizar(ct[["Mês","Total OS","Média de Dias de Conclusão"]]), unsafe_allow_html=True)
        st.markdown("")
        excel_os=gerar_excel_os(df,sla_dias_render,col_num_os,col_responsavel,col_empresa,col_status,col_final)
        st.download_button(label="📥 Exportar Relatório OS Excel",data=excel_os,file_name=f"Relatorio_OS_{datetime.today().strftime('%d%m%Y')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif pagina == "📈 Gráficos — OS":
    import streamlit.components.v1 as components
    st.markdown('<div class="section-title">📈 Gráficos — Ordens de Serviço</div>', unsafe_allow_html=True)
    tab_mes=st.session_state.get("tab_mes_graficos"); nome_arq=st.session_state.get("nome_arquivo_os"); data_arq=st.session_state.get("data_upload_os")
    if tab_mes is None: st.info("Carregue uma planilha na página **🔧 Ordens de Serviço** para visualizar os gráficos.")
    else:
        if nome_arq and data_arq: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {nome_arq} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {data_arq}</div>', unsafe_allow_html=True)
        resumo=st.session_state.get("resumo_executivo")
        if resumo:
            st.markdown('<div class="section-title">Resumo Executivo</div>', unsafe_allow_html=True)
            def br(n): return f"{n:,}".replace(",",".")
            taxa=resumo['taxa_conclusao']
            dt='Alta taxa de conclusão' if taxa>=90 else 'Taxa de conclusão regular' if taxa>=70 else 'Taxa de conclusão baixa'
            media_mensal = round(tab_mes["Finalizadas"].mean(), 1) if tab_mes is not None and "Finalizadas" in tab_mes.columns and len(tab_mes) > 0 else 0
            meses_com_fin = int((tab_mes["Finalizadas"] > 0).sum()) if tab_mes is not None and "Finalizadas" in tab_mes.columns else 0
            sub_media = f"Média em {meses_com_fin} {'mês' if meses_com_fin==1 else 'meses'}" if meses_com_fin > 0 else "Nenhum mês com OS"
            c1,c2,c3,c4,c5=st.columns(5)
            with c1: st.markdown(f'<div class="metric-card"><div class="value">{br(resumo["os_recebidas"])}</div><div style="font-size:0.85rem;font-weight:600;color:#1F4E79;margin-top:4px;">OS Recebidas</div><div class="sub">Total no Período</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="value metric-green">{br(resumo["os_finalizadas"])}</div><div style="font-size:0.85rem;font-weight:600;color:#1a7a4a;margin-top:4px;">OS Finalizadas</div><div class="sub">Total no Período</div></div>', unsafe_allow_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="value">{media_mensal}</div><div style="font-size:0.85rem;font-weight:600;color:#1F4E79;margin-top:4px;">Média / Mês</div><div class="sub">{sub_media}</div></div>', unsafe_allow_html=True)
            with c4: st.markdown(f'<div class="metric-card"><div class="value">{resumo["taxa_conclusao"]}%</div><div style="font-size:0.85rem;font-weight:600;color:#1F4E79;margin-top:4px;">Taxa de Conclusão</div><div class="sub">{dt}</div></div>', unsafe_allow_html=True)
            with c5:
                cor="metric-green" if resumo['pct_dentro_sla']>=80 else "metric-orange" if resumo['pct_dentro_sla']>=60 else "metric-red"
                st.markdown(f'<div class="metric-card"><div class="value {cor}">{resumo["pct_dentro_sla"]}%</div><div style="font-size:0.85rem;font-weight:600;color:#1F4E79;margin-top:4px;">Dentro do SLA</div><div class="sub">Das OS Finalizadas</div></div>', unsafe_allow_html=True)
            st.markdown("")
        labels=tab_mes["Mês"].tolist(); qtd=tab_mes["Finalizadas"].tolist()
        dentro=tab_mes["Dentro_pct"].tolist(); fora=tab_mes["Fora_pct"].tolist()
        st.markdown('<div class="section-title">OS Finalizadas por Mês — SLA</div>', unsafe_allow_html=True)
        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> % Dentro do SLA</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> % Fora do SLA</span>
    <span><span style="width:20px;height:2px;background:#444;display:inline-block;vertical-align:middle;"></span> Finalizadas</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="lineChart"></canvas></div>
  <div style="position:relative;width:100%;height:260px;"><canvas id="barChart"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels};const qtd={qtd};const dentro={dentro};const fora={fora};
let barChart,lineChart;
barChart=new Chart(document.getElementById('barChart').getContext('2d'),{{data:{{labels,datasets:[
  {{type:'bar',label:'% Dentro do SLA',data:dentro,backgroundColor:'#5b8dd9',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}},
  {{type:'bar',label:'% Fora do SLA',data:fora,backgroundColor:'#e8a0a0',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}}
]}},options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLine}},
layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}}}},
scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:12}},color:'#888780'}},border:{{display:false}}}},
y:{{stacked:true,min:0,max:100,ticks:{{callback:v=>v+'%',font:{{size:11}},color:'#888780',stepSize:25}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}}}}},
plugins:[{{id:'barLabels',afterDatasetsDraw(chart){{
  const ctx2=chart.ctx;
  chart.getDatasetMeta(0).data.forEach((bar,i)=>{{ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(dentro[i]+'%',bar.x,bar.y+bar.height/2);ctx2.restore();}});
  chart.getDatasetMeta(1).data.forEach((bar,i)=>{{ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(fora[i]+'%',bar.x,bar.y+bar.height/2);ctx2.restore();}});
}}}}]
}});
function syncLine(){{
  if(!barChart)return;
  const meta=barChart.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barChart.width-xPos[xPos.length-1];
  if(lineChart)lineChart.destroy();
  lineChart=new Chart(document.getElementById('lineChart').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:qtd,borderColor:'#444441',backgroundColor:'#444441',pointBackgroundColor:'#444441',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:Math.min(...qtd)*0.85,max:Math.max(...qtd)*1.1}}}}}},
    plugins:[{{id:'lineLabels',afterDatasetsDraw(chart){{const ctx2=chart.ctx;chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 12px Inter,sans-serif';ctx2.fillStyle='#2c2c2a';ctx2.textAlign='center';ctx2.fillText(qtd[i],pt.x,pt.y-10);ctx2.restore();}});}}}}]
  }});
}}
</script></body></html>""", height=380)

        

        # ── NOVO GRÁFICO: Fluxo Diário Operacional de OS ──────────────────────
        try:
            dados_os = st.session_state.get("dados_os")

            if dados_os:
                df_fluxo = dados_os["df"].copy()

                col_criacao = dados_os.get("col_criacao")
                col_finalizacao = dados_os.get("col_final")

                if col_criacao and col_criacao in df_fluxo.columns:

                    df_fluxo[col_criacao] = pd.to_datetime(
                        df_fluxo[col_criacao],
                        errors="coerce",
                        dayfirst=True
                    )

                    if col_finalizacao and col_finalizacao in df_fluxo.columns:
                        df_fluxo[col_finalizacao] = pd.to_datetime(
                            df_fluxo[col_finalizacao],
                            errors="coerce",
                            dayfirst=True
                        )

                    data_inicio = df_fluxo[col_criacao].min().normalize()
                    data_fim = pd.Timestamp.today().normalize()

                    dias = pd.date_range(data_inicio, data_fim, freq="D")

                    abertura_lista = []
                    entrantes_lista = []
                    encerradas_lista = []
                    saldo_lista = []
                    labels_dias = []

                    saldo_anterior = 0

                    for dia in dias:

                        entrantes = df_fluxo[
                            df_fluxo[col_criacao].dt.normalize() == dia
                        ].shape[0]

                        encerradas = 0

                        if col_finalizacao and col_finalizacao in df_fluxo.columns:
                            encerradas = df_fluxo[
                                df_fluxo[col_finalizacao].dt.normalize() == dia
                            ].shape[0]

                        abertura = saldo_anterior
                        saldo_final = abertura + entrantes - encerradas

                        labels_dias.append(dia.strftime("%d/%m"))
                        abertura_lista.append(int(abertura))
                        entrantes_lista.append(int(entrantes))
                        encerradas_lista.append(int(encerradas))
                        saldo_lista.append(int(saldo_final))

                        saldo_anterior = saldo_final

                    # Filtro de período do gráfico
                    st.markdown(
                        '<div class="section-title">Fluxo Diário Operacional de OS</div>',
                        unsafe_allow_html=True
                    )

                    _fi_default = st.session_state.get("fluxo_os_inicio_salvo") or dias.min().date()
                    _ff_default = st.session_state.get("fluxo_os_fim_salvo") or dias.max().date()

                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        data_inicio_filtro = st.date_input(
                            "Data Inicial",
                            value=_fi_default,
                            format="DD/MM/YYYY",
                            key="fluxo_os_inicio"
                        )
                    with col2:
                        data_fim_filtro = st.date_input(
                            "Data Final",
                            value=_ff_default,
                            format="DD/MM/YYYY",
                            key="fluxo_os_fim"
                        )
                    with col3:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        if st.button("💾 Salvar datas", key="fluxo_os_salvar"):
                            st.session_state["fluxo_os_inicio_salvo"] = st.session_state["fluxo_os_inicio"]
                            st.session_state["fluxo_os_fim_salvo"] = st.session_state["fluxo_os_fim"]
                            st.toast("✅ Datas do Fluxo Diário salvas!", icon="✅")

                    df_grafico = pd.DataFrame({
                        "Data": pd.to_datetime(labels_dias, format="%d/%m"),
                        "Abertura": abertura_lista,
                        "Entrantes": entrantes_lista,
                        "Encerradas": encerradas_lista,
                        "Saldo": saldo_lista
                    })

                    ano_atual = pd.Timestamp.today().year
                    df_grafico["Data"] = df_grafico["Data"].apply(
                        lambda x: x.replace(year=ano_atual)
                    )

                    df_grafico = df_grafico[
                        (df_grafico["Data"].dt.date >= data_inicio_filtro) &
                        (df_grafico["Data"].dt.date <= data_fim_filtro)
                    ]

                    labels_dias = df_grafico["Data"].dt.strftime("%d/%m").tolist()
                    abertura_lista = df_grafico["Abertura"].tolist()
                    entrantes_lista = df_grafico["Entrantes"].tolist()
                    encerradas_lista = df_grafico["Encerradas"].tolist()
                    saldo_lista = df_grafico["Saldo"].tolist()

                    components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#7c8cf8;display:inline-block;"></span> Abertura do Dia</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> Entrantes</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Encerradas</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Saldo Final</span>
  </div>
  <div style="position:relative;width:100%;height:320px;"><canvas id="fluxoDiarioOS"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_dias};
const abertura={abertura_lista};
const entrantes={entrantes_lista};
const encerradas={encerradas_lista};
const saldo={saldo_lista};
new Chart(document.getElementById('fluxoDiarioOS').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'Abertura do Dia',data:abertura,backgroundColor:'#7c8cf8',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Entrantes',data:entrantes,backgroundColor:'#5b8dd9',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Encerradas',data:encerradas,backgroundColor:'#6dbf8b',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Saldo Final',data:saldo,backgroundColor:'#e8a0a0',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780'}},border:{{display:false}}}},
      y:{{beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'barLabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,di)=>{{
      chart.getDatasetMeta(di).data.forEach((bar,i)=>{{
        const val=chart.data.datasets[di].data[i];
        if(val===0)return;
        ctx2.save();ctx2.font='600 10px Inter,sans-serif';
        ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';
        ctx2.fillText(val,bar.x,bar.y+bar.height/2);ctx2.restore();
      }});
    }});
  }}}}]
}});
</script></body></html>""", height=360)

        except Exception as erro_fluxo:
            st.warning(f"Erro ao gerar gráfico diário de OS: {erro_fluxo}")


# ── Gráfico: Recebidas × Finalizadas × Saldo ─────────────────────────────
        if "Recebidas" in tab_mes.columns:
            rec_list=tab_mes["Recebidas"].tolist()
            fin_list=tab_mes["Finalizadas"].tolist()
            sal_list=tab_mes["Saldo"].tolist()
            st.markdown('<div class="section-title">OS por Mês — Recebidas × Finalizadas × Saldo</div>', unsafe_allow_html=True)
            components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> Recebidas</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Finalizadas</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Saldo (não finalizado)</span>
  </div>
  <div style="position:relative;width:100%;height:320px;"><canvas id="rfChart"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels};const rec={rec_list};const fin={fin_list};const sal={sal_list};
new Chart(document.getElementById('rfChart').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'Recebidas',data:rec,backgroundColor:'#5b8dd9',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Finalizadas',data:fin,backgroundColor:'#6dbf8b',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Saldo',data:sal,backgroundColor:'#e8a0a0',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:12}},color:'#888780'}},border:{{display:false}}}},
      y:{{beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'barLabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,di)=>{{
      chart.getDatasetMeta(di).data.forEach((bar,i)=>{{
        const val=chart.data.datasets[di].data[i];
        if(val===0)return;
        ctx2.save();ctx2.font='600 11px Inter,sans-serif';
        ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';
        ctx2.fillText(val,bar.x,bar.y+bar.height/2);ctx2.restore();
      }});
    }});
  }}}}]
}});
</script></body></html>""", height=360)

# ── Gráfico: Performance por Responsável ─────────────────────────────────
        try:
            dados_os_resp = st.session_state.get("dados_os")
            if dados_os_resp:
                df_resp = dados_os_resp["df"].copy()
                col_responsavel_g = dados_os_resp.get("col_responsavel")
                col_final_g       = dados_os_resp.get("col_final")
                col_criacao_g     = dados_os_resp.get("col_criacao") or dados_os_resp.get("col_criacao_g")

                if col_responsavel_g and col_responsavel_g in df_resp.columns and col_final_g and col_final_g in df_resp.columns:

                    df_resp[col_final_g] = pd.to_datetime(df_resp[col_final_g], errors="coerce", dayfirst=True)
                    if col_criacao_g and col_criacao_g in df_resp.columns:
                        df_resp[col_criacao_g] = pd.to_datetime(df_resp[col_criacao_g], errors="coerce", dayfirst=True)

                    df_resp = df_resp[df_resp[col_responsavel_g].astype(str).str.strip().str.lower() != "nan"]

                    st.markdown('<div class="section-title">Performance por Responsável — OS Finalizadas</div>', unsafe_allow_html=True)

                    # ── Filtros ────────────────────────────────────────────
                    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

                    # Datas mínima/máxima do dataset
                    datas_validas = df_resp[col_final_g].dropna()
                    if col_criacao_g and col_criacao_g in df_resp.columns:
                        datas_validas_cria = df_resp[col_criacao_g].dropna()
                        data_min_resp = min(datas_validas.min(), datas_validas_cria.min()).date() if len(datas_validas) and len(datas_validas_cria) else (datas_validas.min().date() if len(datas_validas) else pd.Timestamp.today().date())
                    else:
                        data_min_resp = datas_validas.min().date() if len(datas_validas) else pd.Timestamp.today().date()
                    data_max_resp = pd.Timestamp.today().date()

                    _pri_default = st.session_state.get("perf_resp_inicio_salvo") or data_min_resp
                    _prf_default = st.session_state.get("perf_resp_fim_salvo") or data_max_resp

                    with col_f1:
                        resp_inicio = st.date_input("Data Inicial", value=_pri_default, format="DD/MM/YYYY", key="perf_resp_inicio")
                    with col_f2:
                        resp_fim = st.date_input("Data Final", value=_prf_default, format="DD/MM/YYYY", key="perf_resp_fim")

                    # Lista de responsáveis ordenada
                    lista_responsaveis = sorted(df_resp[col_responsavel_g].dropna().astype(str).str.strip().unique().tolist())
                    with col_f3:
                        resp_selecionados = st.multiselect(
                            "Responsável(is)",
                            options=lista_responsaveis,
                            default=[],
                            placeholder="Todos os responsáveis",
                            key="perf_resp_select"
                        )

                    col_f4, _ = st.columns([1, 3])
                    with col_f4:
                        if st.button("💾 Salvar datas", key="perf_resp_salvar"):
                            st.session_state["perf_resp_inicio_salvo"] = st.session_state["perf_resp_inicio"]
                            st.session_state["perf_resp_fim_salvo"] = st.session_state["perf_resp_fim"]
                            st.toast("✅ Datas da Performance por Responsável salvas!", icon="✅")

                    # ── Aplicar filtro de datas ────────────────────────────
                    # OS criadas no período (independente de estar finalizada ou não)
                    mask_periodo = pd.Series([False] * len(df_resp), index=df_resp.index)
                    if col_criacao_g and col_criacao_g in df_resp.columns:
                        mask_periodo |= (
                            (df_resp[col_criacao_g].dt.date >= resp_inicio) &
                            (df_resp[col_criacao_g].dt.date <= resp_fim)
                        )
                    # OS finalizadas no período (mesmo que criadas fora)
                    mask_fin_periodo = df_resp[col_final_g].notna() & (
                        (df_resp[col_final_g].dt.date >= resp_inicio) &
                        (df_resp[col_final_g].dt.date <= resp_fim)
                    )
                    mask_periodo |= mask_fin_periodo

                    # OS em andamento (sem finalização) — sempre incluídas para mostrar carteira atual
                    mask_em_aberto = df_resp[col_final_g].isna()
                    mask_total = mask_periodo | mask_em_aberto

                    df_periodo = df_resp[mask_total].copy()

                    # Filtro por responsável selecionado
                    if resp_selecionados:
                        df_periodo = df_periodo[df_periodo[col_responsavel_g].astype(str).str.strip().isin(resp_selecionados)]

                    if len(df_periodo) == 0:
                        st.info("Nenhuma OS encontrada para os filtros selecionados.")
                    else:
                        # ── Gráfico 1: Visão geral por responsável ─────────
                        # Finalizadas: somente as finalizadas dentro do período selecionado
                        finalizadas_no_periodo = df_periodo[
                            df_periodo[col_final_g].notna() &
                            (df_periodo[col_final_g].dt.date >= resp_inicio) &
                            (df_periodo[col_final_g].dt.date <= resp_fim)
                        ]
                        # Em aberto: OS sem data de finalização (carteira atual do responsável)
                        em_aberto_df = df_periodo[df_periodo[col_final_g].isna()]

                        fin_resp    = finalizadas_no_periodo.groupby(col_responsavel_g).size().reset_index(name="Finalizadas")
                        aberto_resp = em_aberto_df.groupby(col_responsavel_g).size().reset_index(name="Em Aberto")
                        perf        = fin_resp.merge(aberto_resp, on=col_responsavel_g, how="outer").fillna(0)
                        perf["Finalizadas"] = perf["Finalizadas"].astype(int)
                        perf["Em Aberto"]   = perf["Em Aberto"].astype(int)
                        perf["Total"]       = perf["Finalizadas"] + perf["Em Aberto"]
                        perf["Taxa (%)"]    = (perf["Finalizadas"] / perf["Total"] * 100).round(1)
                        perf = perf.sort_values("Finalizadas", ascending=False).head(20)

                        responsaveis_list = perf[col_responsavel_g].tolist()
                        finalizadas_list  = perf["Finalizadas"].tolist()
                        aberto_list       = perf["Em Aberto"].tolist()
                        taxa_list         = perf["Taxa (%)"].tolist()

                        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Finalizadas no período</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Em Aberto</span>
    <span><span style="width:20px;height:2px;background:#444;display:inline-block;vertical-align:middle;"></span> Taxa de Conclusão (%)</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="lineRespChart"></canvas></div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="barRespChart"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={responsaveis_list};
const fin={finalizadas_list};
const aberto={aberto_list};
const taxa={taxa_list};
let barRespChart,lineRespChart;
barRespChart=new Chart(document.getElementById('barRespChart').getContext('2d'),{{
  data:{{labels,datasets:[
    {{type:'bar',label:'Finalizadas',data:fin,backgroundColor:'#6dbf8b',stack:'resp',barPercentage:0.5,categoryPercentage:0.65}},
    {{type:'bar',label:'Em Aberto',data:aberto,backgroundColor:'#e8a0a0',stack:'resp',barPercentage:0.5,categoryPercentage:0.65}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLineResp}},
    layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{stacked:true,beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'barRespLabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.getDatasetMeta(0).data.forEach((bar,i)=>{{
      if(fin[i]===0)return;
      ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';
      ctx2.fillText(fin[i],bar.x,bar.y+bar.height/2);ctx2.restore();
    }});
    chart.getDatasetMeta(1).data.forEach((bar,i)=>{{
      if(aberto[i]===0)return;
      ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';
      ctx2.fillText(aberto[i],bar.x,bar.y+bar.height/2);ctx2.restore();
    }});
  }}}}]
}});
function syncLineResp(){{
  if(!barRespChart)return;
  const meta=barRespChart.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barRespChart.width-xPos[xPos.length-1];
  if(lineRespChart)lineRespChart.destroy();
  lineRespChart=new Chart(document.getElementById('lineRespChart').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:taxa,borderColor:'#444441',backgroundColor:'#444441',pointBackgroundColor:'#444441',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:0,max:110}}}}}},
    plugins:[{{id:'lineRespLabels',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;
      chart.getDatasetMeta(0).data.forEach((pt,i)=>{{
        ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#2c2c2a';ctx2.textAlign='center';
        ctx2.fillText(taxa[i]+'%',pt.x,pt.y-10);ctx2.restore();
      }});
    }}}}]
  }});
}}
</script></body></html>""", height=420)

                        # ── Gráfico 2: Atividade diária do(s) responsável(is) selecionado(s) ──
                        if resp_selecionados and col_criacao_g and col_criacao_g in df_resp.columns:
                            for nome_resp in resp_selecionados:
                                # Usa df_resp completo (sem corte de período) para saldo real
                                df_um_full = df_resp[df_resp[col_responsavel_g].astype(str).str.strip() == nome_resp].copy()
                                if len(df_um_full) == 0:
                                    continue

                                dias_range = pd.date_range(resp_inicio, resp_fim, freq="D")
                                labels_d, total_dia_list, fin_dia_list, saldo_dia_list = [], [], [], []

                                for dia in dias_range:
                                    ts_dia = pd.Timestamp(dia)
                                    # Carteira do dia: criadas até o dia e não finalizadas antes dele
                                    criadas_ate = df_um_full[df_um_full[col_criacao_g].dt.normalize() <= ts_dia]
                                    finalizadas_antes = criadas_ate[
                                        criadas_ate[col_final_g].notna() &
                                        (criadas_ate[col_final_g].dt.normalize() < ts_dia)
                                    ]
                                    total_no_dia = len(criadas_ate) - len(finalizadas_antes)

                                    # Finalizadas neste dia
                                    fin_no_dia = df_um_full[
                                        df_um_full[col_final_g].notna() &
                                        (df_um_full[col_final_g].dt.normalize() == ts_dia)
                                    ].shape[0]

                                    # Saldo = carteira do dia - finalizadas no dia
                                    saldo_no_dia = total_no_dia - fin_no_dia

                                    labels_d.append(dia.strftime("%d/%m"))
                                    total_dia_list.append(int(total_no_dia))
                                    fin_dia_list.append(int(fin_no_dia))
                                    saldo_dia_list.append(int(saldo_no_dia))

                                # Remove dias completamente zerados das bordas
                                df_diario = pd.DataFrame({"label": labels_d, "total": total_dia_list, "fin": fin_dia_list, "saldo": saldo_dia_list})
                                primeiro = df_diario[(df_diario["total"] > 0) | (df_diario["fin"] > 0)].index.min()
                                if pd.notna(primeiro):
                                    df_diario = df_diario.loc[primeiro:]

                                labels_d       = df_diario["label"].tolist()
                                total_dia_list = df_diario["total"].tolist()
                                fin_dia_list   = df_diario["fin"].tolist()
                                saldo_dia_list = df_diario["saldo"].tolist()

                                # Saldo atual = OS sem finalização (carteira viva hoje)
                                saldo_atual = int(df_um_full[df_um_full[col_final_g].isna()].shape[0])

                                _cid = nome_resp.replace(' ','_').replace('/','_').replace('.','_')
                                st.markdown(
                                    f'<div class="section-title">📅 Atividade Diária — {nome_resp} ' +
                                    f'&nbsp;<span style="font-size:0.82rem;font-weight:500;color:#888;">Saldo atual: ' +
                                    f'<b style="color:#e05a5a">{saldo_atual} OS em aberto</b></span></div>',
                                    unsafe_allow_html=True
                                )
                                _saldo_max = max(saldo_dia_list) if saldo_dia_list else 1
                                components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> OS no Dia (carteira)</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Finalizadas no Dia</span>
    <span><span style="width:20px;height:2px;background:#e05a5a;display:inline-block;vertical-align:middle;"></span> Saldo do Dia</span>
  </div>
  <div style="position:relative;width:100%;height:72px;"><canvas id="lineSaldo_{_cid}"></canvas></div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="diarioResp_{_cid}"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_d};
const total={total_dia_list};
const fin={fin_dia_list};
const saldo={saldo_dia_list};
let barDiario,lineSaldo;
barDiario=new Chart(document.getElementById('diarioResp_{_cid}').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'OS no Dia',data:total,backgroundColor:'#5b8dd9',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Finalizadas',data:fin,backgroundColor:'#6dbf8b',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,
    animation:{{onComplete:syncSaldo}},
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'lblDiario',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,di)=>{{
      chart.getDatasetMeta(di).data.forEach((bar,i)=>{{
        const val=chart.data.datasets[di].data[i];
        if(val===0)return;
        ctx2.save();ctx2.font='600 10px Inter,sans-serif';
        ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';
        ctx2.fillText(val,bar.x,bar.y+bar.height/2);ctx2.restore();
      }});
    }});
  }}}}]
}});
function syncSaldo(){{
  if(!barDiario)return;
  const meta=barDiario.getDatasetMeta(0);
  const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0]; const rp=barDiario.width-xPos[xPos.length-1];
  if(lineSaldo)lineSaldo.destroy();
  lineSaldo=new Chart(document.getElementById('lineSaldo_{_cid}').getContext('2d'),{{
    type:'line',
    data:{{labels,datasets:[{{
      data:saldo,borderColor:'#e05a5a',backgroundColor:'#e05a5a',
      pointBackgroundColor:'#e05a5a',pointRadius:5,pointHoverRadius:7,
      borderWidth:2,tension:0
    }}]}},
    options:{{
      responsive:true,maintainAspectRatio:false,
      layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},
      plugins:{{legend:{{display:false}}}},
      scales:{{x:{{display:false}},y:{{display:false,min:0,max:{_saldo_max}*1.5+1}}}}
    }},
    plugins:[{{id:'lblSaldo',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;
      chart.getDatasetMeta(0).data.forEach((pt,i)=>{{
        ctx2.save();ctx2.font='600 11px Inter,sans-serif';
        ctx2.fillStyle='#c0392b';ctx2.textAlign='center';
        ctx2.fillText(saldo[i],pt.x,pt.y-10);ctx2.restore();
      }});
    }}}}]
  }});
}}
</script></body></html>""", height=420)

        except Exception as erro_resp:
            st.warning(f"Erro ao gerar gráfico de performance por responsável: {erro_resp}")

elif pagina == "📄 Status Atual — OS":
    st.markdown('<div class="section-title">📄 Status Atual — OS</div>', unsafe_allow_html=True)
    ig=buscar_status_info_github()
    na=st.session_state.get("nome_arquivo_os") or (ig.get("nome_arquivo") if ig else None)
    da=st.session_state.get("data_upload_os") or (ig.get("data_upload") if ig else None)
    if na and da: st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {na} &nbsp;|&nbsp; 🕐 <b>Última atualização:</b> {da}</div>', unsafe_allow_html=True)
    else: st.info("Carregue uma planilha em **🔧 Ordens de Serviço** para gerar o Status Atual.")
    with st.spinner("Buscando PDF..."):
        pdf_content,erro=baixar_pdf_github()
    if pdf_content: st.download_button(label="📥 Baixar Status Atual (PDF)",data=pdf_content,file_name="Status_Atual_OS.pdf",mime="application/pdf")
    elif erro: st.info(erro)

elif pagina == "👤 Desempenho Individual":
    import streamlit.components.v1 as components
    import json as _json
    st.markdown('<div class="section-title">👤 Desempenho Individual — Ordens de Serviço</div>', unsafe_allow_html=True)
    st.markdown("""<div style="background:#f8fafc;border-left:3px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#555;">
        Este módulo utiliza uma planilha de OS <b>exclusiva</b>, independente da planilha carregada em <b>🔧 Ordens de Serviço</b>.
        Os dados são salvos automaticamente e restaurados ao reabrir o sistema.
    </div>""", unsafe_allow_html=True)

    sla_dias_di = st.number_input("SLA (dias úteis)", min_value=1, max_value=30, value=st.session_state.sla_dias, key="sla_di_input")

    arquivo_di = st.file_uploader("Selecione a planilha de OS (Desempenho Individual)", type=["xlsx"], key="upload_os_individual")
    if arquivo_di:
        with st.spinner("Analisando OS..."):
            bytes_di = arquivo_di.getvalue()
            resultado_di = analisar_os_individual(bytes_di, sla_dias_di)
        if len(resultado_di) == 3:
            df_di, erro_di, meta_di = resultado_di
        else:
            df_di, erro_di, meta_di = None, "Erro desconhecido", {}

        if erro_di:
            st.error(f"Erro ao processar planilha: {erro_di}")
        else:
            st.session_state.nome_arquivo_os_individual = arquivo_di.name
            st.session_state.data_upload_os_individual = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
            st.session_state.dados_os_individual = {**meta_di, "df": df_di}
            with st.spinner("Salvando dados..."):
                salvar_estado_github(salvar_dfs=True)
            st.toast("✅ Planilha salva com sucesso!", icon="✅")

    dados_di = st.session_state.get("dados_os_individual")
    if dados_di is None:
        st.info("Selecione uma planilha de OS para iniciar a análise de desempenho individual.")
    else:
        df_di         = dados_di["df"]
        col_resp_di   = dados_di.get("col_responsavel")
        col_final_di  = dados_di.get("col_final")
        col_cria_di   = dados_di.get("col_criacao")
        col_stat_di   = dados_di.get("col_status")
        col_nos_di    = dados_di.get("col_num_os")
        col_emp_di    = dados_di.get("col_empresa")
        col_banco_di  = dados_di.get("col_banco")
        sla_d_di      = dados_di.get("sla_dias", sla_dias_di)

        # Garantir tipos de data corretos após restauração
        for _dc in [col_cria_di, col_final_di]:
            if _dc and _dc in df_di.columns:
                df_di[_dc] = pd.to_datetime(df_di[_dc], errors="coerce")

        nome_di = st.session_state.get("nome_arquivo_os_individual")
        data_di = st.session_state.get("data_upload_os_individual")
        if nome_di and data_di:
            st.markdown(f'<div style="background:#f0f4f8;border-left:4px solid #1F4E79;border-radius:6px;padding:10px 16px;margin-bottom:1rem;font-size:0.85rem;color:#444;">📂 <b>Planilha:</b> {nome_di} &nbsp;|&nbsp; 🕐 <b>Carregada em:</b> {data_di}</div>', unsafe_allow_html=True)

        finalizadas_di = df_di[df_di["Status Calculado"] == "Finalizada"]
        andamento_di   = df_di[df_di["Status Calculado"] != "Finalizada"]
        dentro_di      = andamento_di[andamento_di["Dentro SLA"]]
        fora_di        = andamento_di[~andamento_di["Dentro SLA"]]

        # ── Cards de resumo ────────────────────────────────────────────────
        st.markdown('<div class="section-title">Resumo Geral</div>', unsafe_allow_html=True)
        pct_dentro_di = round(len(dentro_di)/len(andamento_di)*100, 1) if len(andamento_di) > 0 else 0
        pct_fora_di   = round(len(fora_di)/len(andamento_di)*100, 1)   if len(andamento_di) > 0 else 0
        # % SLA das finalizadas
        fin_sla = finalizadas_di[finalizadas_di["Dentro SLA"]].shape[0] if "Dentro SLA" in finalizadas_di.columns else 0
        pct_fin_sla = round(fin_sla/len(finalizadas_di)*100, 1) if len(finalizadas_di) > 0 else 0
        media_dias = round(finalizadas_di["Dias Uteis"].mean(), 1) if len(finalizadas_di) > 0 else 0

        c1,c2,c3,c4,c5 = st.columns(5)
        with c1: st.markdown(f'<div class="metric-card"><div class="label">Total OS</div><div class="value">{len(df_di)}</div><div class="sub">Na planilha</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card metric-green"><div class="label">Finalizadas</div><div class="value">{len(finalizadas_di)}</div><div class="sub">{round(len(finalizadas_di)/len(df_di)*100,1) if len(df_di)>0 else 0}% do total</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="label">Em Andamento</div><div class="value">{len(andamento_di)}</div><div class="sub">{round(len(andamento_di)/len(df_di)*100,1) if len(df_di)>0 else 0}% do total</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card metric-green"><div class="label">% SLA (Finalizadas)</div><div class="value">{pct_fin_sla}%</div><div class="sub">{fin_sla} dentro de {len(finalizadas_di)}</div></div>', unsafe_allow_html=True)
        with c5: st.markdown(f'<div class="metric-card"><div class="label">Média Dias (Fin.)</div><div class="value">{media_dias}</div><div class="sub">Dias por OS finalizada</div></div>', unsafe_allow_html=True)
        st.markdown("")

        # ── Gráfico 1: OS Finalizadas por Mês — SLA ───────────────────────
        if col_final_di and col_final_di in df_di.columns and len(finalizadas_di) > 0:
            st.markdown('<div class="section-title">OS Finalizadas por Mês — SLA</div>', unsafe_allow_html=True)
            fin_cp = finalizadas_di.copy()
            fin_cp["_Mes"] = fin_cp[col_final_di].dt.to_period("M")
            tab_mes_di = fin_cp.groupby("_Mes").agg(
                Finalizadas=("_Mes","count"), Dentro=("Dentro SLA","sum")
            ).reset_index()
            tab_mes_di["Fora"]       = tab_mes_di["Finalizadas"] - tab_mes_di["Dentro"]
            tab_mes_di["Dentro_pct"] = (tab_mes_di["Dentro"]/tab_mes_di["Finalizadas"]*100).round(0).astype(int)
            tab_mes_di["Fora_pct"]   = (tab_mes_di["Fora"]/tab_mes_di["Finalizadas"]*100).round(0).astype(int)
            tab_mes_di["Mês"]        = tab_mes_di["_Mes"].apply(lambda m: mes_abrev(str(m)))

            labels_di_m    = tab_mes_di["Mês"].tolist()
            qtd_di_m       = tab_mes_di["Finalizadas"].tolist()
            dentro_pct_di  = tab_mes_di["Dentro_pct"].tolist()
            fora_pct_di    = tab_mes_di["Fora_pct"].tolist()

            components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> % Dentro do SLA</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> % Fora do SLA</span>
    <span><span style="width:20px;height:2px;background:#444;display:inline-block;vertical-align:middle;"></span> Finalizadas</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="diLineChart"></canvas></div>
  <div style="position:relative;width:100%;height:260px;"><canvas id="diBarChart"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_di_m};const qtd={qtd_di_m};const dentro={dentro_pct_di};const fora={fora_pct_di};
let barChart,lineChart;
barChart=new Chart(document.getElementById('diBarChart').getContext('2d'),{{data:{{labels,datasets:[
  {{type:'bar',label:'% Dentro do SLA',data:dentro,backgroundColor:'#5b8dd9',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}},
  {{type:'bar',label:'% Fora do SLA',data:fora,backgroundColor:'#e8a0a0',stack:'sla',barPercentage:0.5,categoryPercentage:0.65}}
]}},options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLine}},
layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}}}},
scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:12}},color:'#888780'}},border:{{display:false}}}},
y:{{stacked:true,min:0,max:100,ticks:{{callback:v=>v+'%',font:{{size:11}},color:'#888780',stepSize:25}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}}}}},
plugins:[{{id:'barLabels',afterDatasetsDraw(chart){{
  const ctx2=chart.ctx;
  chart.getDatasetMeta(0).data.forEach((bar,i)=>{{ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(dentro[i]+'%',bar.x,bar.y+bar.height/2);ctx2.restore();}});
  chart.getDatasetMeta(1).data.forEach((bar,i)=>{{ctx2.save();ctx2.font='500 11px Inter,sans-serif';ctx2.fillStyle='#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(fora[i]+'%',bar.x,bar.y+bar.height/2);ctx2.restore();}});
}}}}]
}});
function syncLine(){{
  if(!barChart)return;
  const meta=barChart.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barChart.width-xPos[xPos.length-1];
  if(lineChart)lineChart.destroy();
  lineChart=new Chart(document.getElementById('diLineChart').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:qtd,borderColor:'#444441',backgroundColor:'#444441',pointBackgroundColor:'#444441',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:Math.min(...qtd)*0.85,max:Math.max(...qtd)*1.1}}}}}},
    plugins:[{{id:'lineLabels',afterDatasetsDraw(chart){{const ctx2=chart.ctx;chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 12px Inter,sans-serif';ctx2.fillStyle='#2c2c2a';ctx2.textAlign='center';ctx2.fillText(qtd[i],pt.x,pt.y-10);ctx2.restore();}});}}}}]
  }});
}}
</script></body></html>""", height=380)
            st.markdown(estilizar_tab_mes(tab_mes_di), unsafe_allow_html=True)
            st.markdown("")

        # ── Gráfico 2: Performance por Responsável ─────────────────────────
        if col_resp_di and col_resp_di in df_di.columns:
            df_resp_di = df_di[df_di[col_resp_di].astype(str).str.strip().str.lower().isin(["nan","none","","<na>"]) == False].copy()

            if col_cria_di and col_cria_di in df_resp_di.columns:
                df_resp_di[col_cria_di] = pd.to_datetime(df_resp_di[col_cria_di], errors="coerce")
            if col_final_di and col_final_di in df_resp_di.columns:
                df_resp_di[col_final_di] = pd.to_datetime(df_resp_di[col_final_di], errors="coerce")

            datas_cria_di    = df_resp_di[col_cria_di].dropna() if col_cria_di and col_cria_di in df_resp_di.columns else pd.Series(dtype="datetime64[ns]")
            datas_final_di   = df_resp_di[col_final_di].dropna() if col_final_di and col_final_di in df_resp_di.columns else pd.Series(dtype="datetime64[ns]")
            _all_dates = pd.concat([datas_cria_di, datas_final_di]).dropna()
            data_min_di = _all_dates.min().date() if len(_all_dates) > 0 else datetime.today().date()
            data_max_di = datetime.today().date()

            _di_ini_def = st.session_state.get("di_resp_inicio_salvo") or data_min_di
            _di_fim_def = st.session_state.get("di_resp_fim_salvo") or data_max_di

            st.markdown('<div class="section-title">Performance por Responsável</div>', unsafe_allow_html=True)
            colf1, colf2, colf3 = st.columns([1,1,2])
            with colf1:
                di_inicio = st.date_input("Data Inicial", value=_di_ini_def, format="DD/MM/YYYY", key="di_resp_inicio")
            with colf2:
                di_fim    = st.date_input("Data Final",   value=_di_fim_def, format="DD/MM/YYYY", key="di_resp_fim")
            with colf3:
                lista_resp_di = sorted(df_resp_di[col_resp_di].dropna().astype(str).str.strip().unique().tolist())
                resp_di_sel   = st.multiselect("Responsável(is)", options=lista_resp_di, default=[], placeholder="Todos os responsáveis", key="di_resp_sel")

            colsv, _ = st.columns([1,3])
            with colsv:
                if st.button("💾 Salvar datas", key="di_resp_salvar"):
                    st.session_state["di_resp_inicio_salvo"] = st.session_state["di_resp_inicio"]
                    st.session_state["di_resp_fim_salvo"]    = st.session_state["di_resp_fim"]
                    st.toast("✅ Datas salvas!", icon="✅")

            # Filtrar período
            mask_di = pd.Series([False]*len(df_resp_di), index=df_resp_di.index)
            if col_cria_di and col_cria_di in df_resp_di.columns:
                mask_di |= (df_resp_di[col_cria_di].dt.date >= di_inicio) & (df_resp_di[col_cria_di].dt.date <= di_fim)
            if col_final_di and col_final_di in df_resp_di.columns:
                mask_di |= df_resp_di[col_final_di].notna() & (df_resp_di[col_final_di].dt.date >= di_inicio) & (df_resp_di[col_final_di].dt.date <= di_fim)
            if col_final_di and col_final_di in df_resp_di.columns:
                mask_di |= df_resp_di[col_final_di].isna()
            df_per_di = df_resp_di[mask_di].copy()
            if resp_di_sel:
                df_per_di = df_per_di[df_per_di[col_resp_di].astype(str).str.strip().isin(resp_di_sel)]

            if len(df_per_di) == 0:
                st.info("Nenhuma OS encontrada para os filtros selecionados.")
            else:
                fin_per_di    = df_per_di[df_per_di["Status Calculado"] == "Finalizada"] if "Status Calculado" in df_per_di.columns else df_per_di
                aberto_per_di = df_per_di[df_per_di["Status Calculado"] != "Finalizada"] if "Status Calculado" in df_per_di.columns else pd.DataFrame()

                # Somente finalizadas no período selecionado
                if col_final_di and col_final_di in fin_per_di.columns:
                    fin_per_di = fin_per_di[fin_per_di[col_final_di].notna() & (fin_per_di[col_final_di].dt.date >= di_inicio) & (fin_per_di[col_final_di].dt.date <= di_fim)]

                fin_r    = fin_per_di.groupby(col_resp_di).size().reset_index(name="Finalizadas")
                abr_r    = aberto_per_di.groupby(col_resp_di).size().reset_index(name="Em Aberto") if len(aberto_per_di) > 0 else pd.DataFrame(columns=[col_resp_di,"Em Aberto"])
                sla_r    = fin_per_di[fin_per_di["Dentro SLA"]].groupby(col_resp_di).size().reset_index(name="Dentro SLA") if "Dentro SLA" in fin_per_di.columns and len(fin_per_di) > 0 else pd.DataFrame(columns=[col_resp_di,"Dentro SLA"])
                dias_r   = fin_per_di.groupby(col_resp_di)["Dias Uteis"].mean().reset_index().rename(columns={"Dias Uteis":"Media Dias"}) if "Dias Uteis" in fin_per_di.columns else pd.DataFrame(columns=[col_resp_di,"Media Dias"])

                perf_di = fin_r.merge(abr_r, on=col_resp_di, how="outer").merge(sla_r, on=col_resp_di, how="left").merge(dias_r, on=col_resp_di, how="left").fillna(0)
                perf_di["Finalizadas"] = perf_di["Finalizadas"].astype(int)
                perf_di["Em Aberto"]   = perf_di["Em Aberto"].astype(int)
                perf_di["Dentro SLA"]  = perf_di["Dentro SLA"].astype(int)
                perf_di["Total"]       = perf_di["Finalizadas"] + perf_di["Em Aberto"]
                perf_di["Taxa (%)"]    = (perf_di["Finalizadas"] / perf_di["Total"].replace(0,1) * 100).round(1)
                perf_di["% SLA"]       = (perf_di["Dentro SLA"] / perf_di["Finalizadas"].replace(0,1) * 100).round(1)
                perf_di["Média Dias"]  = perf_di["Media Dias"].round(1)
                perf_di = perf_di.sort_values("Finalizadas", ascending=False).head(20)

                resp_list_di = perf_di[col_resp_di].tolist()
                fin_list_di  = perf_di["Finalizadas"].tolist()
                abr_list_di  = perf_di["Em Aberto"].tolist()
                taxa_list_di = perf_di["Taxa (%)"].tolist()
                sla_list_di  = perf_di["% SLA"].tolist()

                components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Finalizadas no período</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#e8a0a0;display:inline-block;"></span> Em Aberto</span>
    <span><span style="width:20px;height:2px;background:#2563eb;display:inline-block;vertical-align:middle;"></span> Taxa Conclusão (%)</span>
    <span><span style="width:20px;border-top:3px dashed #10b981;display:inline-block;vertical-align:middle;"></span> % Dentro SLA</span>
  </div>
  <div style="position:relative;width:100%;height:80px;"><canvas id="diLineResp"></canvas></div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="diBarResp"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={_json.dumps(resp_list_di)};
const fin={fin_list_di};const aberto={abr_list_di};const taxa={taxa_list_di};const sla={sla_list_di};
let barDI,lineDI;
barDI=new Chart(document.getElementById('diBarResp').getContext('2d'),{{
  data:{{labels,datasets:[
    {{type:'bar',label:'Finalizadas',data:fin,backgroundColor:'#6dbf8b',stack:'di',barPercentage:0.5,categoryPercentage:0.65}},
    {{type:'bar',label:'Em Aberto',data:aberto,backgroundColor:'#e8a0a0',stack:'di',barPercentage:0.5,categoryPercentage:0.65}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncLineDI}},
    layout:{{padding:{{left:0,right:0,bottom:4}}}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{stacked:true,beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'barDILabels',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.getDatasetMeta(0).data.forEach((bar,i)=>{{if(fin[i]===0)return;ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(fin[i],bar.x,bar.y+bar.height/2);ctx2.restore();}});
    chart.getDatasetMeta(1).data.forEach((bar,i)=>{{if(aberto[i]===0)return;ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#8b3a3a';ctx2.textAlign='center';ctx2.textBaseline='middle';ctx2.fillText(aberto[i],bar.x,bar.y+bar.height/2);ctx2.restore();}});
  }}}}]
}});
function syncLineDI(){{
  if(!barDI)return;
  const meta=barDI.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barDI.width-xPos[xPos.length-1];
  if(lineDI)lineDI.destroy();
  lineDI=new Chart(document.getElementById('diLineResp').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[
      {{data:taxa,borderColor:'#2563eb',backgroundColor:'#2563eb',pointBackgroundColor:'#2563eb',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0,label:'Taxa'}},
      {{data:sla,borderColor:'#10b981',backgroundColor:'#10b981',pointBackgroundColor:'#10b981',pointRadius:4,pointHoverRadius:6,borderWidth:2,tension:0,borderDash:[5,4],label:'SLA'}}
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:0,max:115}}}}}},
    plugins:[{{id:'lineDILabels',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;
      chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 10px Inter,sans-serif';ctx2.fillStyle='#1e3a5f';ctx2.textAlign='center';ctx2.fillText(taxa[i]+'%',pt.x,pt.y-9);ctx2.restore();}});
      chart.getDatasetMeta(1).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='500 10px Inter,sans-serif';ctx2.fillStyle='#065f46';ctx2.textAlign='center';ctx2.fillText(sla[i]+'%',pt.x,pt.y+14);ctx2.restore();}});
    }}}}]
  }});
}}
</script></body></html>""", height=420)

                # Tabela de performance
                st.markdown('<div class="section-title">Tabela de Desempenho por Responsável</div>', unsafe_allow_html=True)
                tab_perf_di = perf_di[[col_resp_di,"Finalizadas","Em Aberto","Total","Taxa (%)","Dentro SLA","% SLA","Média Dias"]].copy()
                tab_perf_di = tab_perf_di.rename(columns={col_resp_di:"Responsável","% SLA":"% Dentro SLA"})
                st.markdown(estilizar(tab_perf_di), unsafe_allow_html=True)
                st.markdown("")

                # ── Atividade Diária por responsável selecionado ───────────
                if resp_di_sel and col_cria_di and col_cria_di in df_resp_di.columns:
                    for nome_di_r in resp_di_sel:
                        df_um_di = df_resp_di[df_resp_di[col_resp_di].astype(str).str.strip() == nome_di_r].copy()
                        if len(df_um_di) == 0:
                            continue

                        dias_r_di = pd.date_range(di_inicio, di_fim, freq="D")
                        labels_ddi, total_ddi, fin_ddi, saldo_ddi = [], [], [], []

                        for dia in dias_r_di:
                            ts_dia = pd.Timestamp(dia)
                            criadas_ate = df_um_di[df_um_di[col_cria_di].dt.normalize() <= ts_dia]
                            if col_final_di and col_final_di in df_um_di.columns:
                                finalizadas_antes = criadas_ate[criadas_ate[col_final_di].notna() & (criadas_ate[col_final_di].dt.normalize() < ts_dia)]
                                total_no_dia = len(criadas_ate) - len(finalizadas_antes)
                                fin_no_dia   = int(df_um_di[df_um_di[col_final_di].notna() & (df_um_di[col_final_di].dt.normalize() == ts_dia)].shape[0])
                            else:
                                total_no_dia = len(criadas_ate)
                                fin_no_dia   = 0
                            saldo_no_dia = total_no_dia - fin_no_dia
                            labels_ddi.append(dia.strftime("%d/%m"))
                            total_ddi.append(int(total_no_dia))
                            fin_ddi.append(int(fin_no_dia))
                            saldo_ddi.append(int(saldo_no_dia))

                        df_ddi_df = pd.DataFrame({"label":labels_ddi,"total":total_ddi,"fin":fin_ddi,"saldo":saldo_ddi})
                        primeiro_ddi = df_ddi_df[(df_ddi_df["total"]>0)|(df_ddi_df["fin"]>0)].index.min()
                        if pd.notna(primeiro_ddi):
                            df_ddi_df = df_ddi_df.loc[primeiro_ddi:]
                        labels_ddi = df_ddi_df["label"].tolist()
                        total_ddi  = df_ddi_df["total"].tolist()
                        fin_ddi    = df_ddi_df["fin"].tolist()
                        saldo_ddi  = df_ddi_df["saldo"].tolist()

                        saldo_atual_di = int(df_um_di[df_um_di[col_final_di].isna()].shape[0]) if col_final_di and col_final_di in df_um_di.columns else 0
                        _saldo_max_di  = max(saldo_ddi) if saldo_ddi else 1
                        _cid_di = nome_di_r.replace(" ","_").replace("/","_").replace(".","_")

                        st.markdown(
                            f'<div class="section-title">📅 Atividade Diária — {nome_di_r} '
                            f'&nbsp;<span style="font-size:0.82rem;font-weight:500;color:#888;">Saldo atual: '
                            f'<b style="color:#e05a5a">{saldo_atual_di} OS em aberto</b></span></div>',
                            unsafe_allow_html=True
                        )
                        components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:transparent;font-family:'Inter',sans-serif;">
<div style="padding:8px 0 0 0;">
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px;font-size:12px;color:#666;justify-content:center;">
    <span><span style="width:10px;height:10px;border-radius:2px;background:#5b8dd9;display:inline-block;"></span> OS no Dia (carteira)</span>
    <span><span style="width:10px;height:10px;border-radius:2px;background:#6dbf8b;display:inline-block;"></span> Finalizadas no Dia</span>
    <span><span style="width:20px;height:2px;background:#e05a5a;display:inline-block;vertical-align:middle;"></span> Saldo do Dia</span>
  </div>
  <div style="position:relative;width:100%;height:72px;"><canvas id="lineSaldo_{_cid_di}"></canvas></div>
  <div style="position:relative;width:100%;height:300px;"><canvas id="diarioDI_{_cid_di}"></canvas></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const labels={labels_ddi};const total={total_ddi};const fin={fin_ddi};const saldo={saldo_ddi};
let barDiDI,lineSaldoDI;
barDiDI=new Chart(document.getElementById('diarioDI_{_cid_di}').getContext('2d'),{{
  type:'bar',
  data:{{labels,datasets:[
    {{label:'OS no Dia',data:total,backgroundColor:'#5b8dd9',barPercentage:0.6,categoryPercentage:0.7}},
    {{label:'Finalizadas',data:fin,backgroundColor:'#6dbf8b',barPercentage:0.6,categoryPercentage:0.7}}
  ]}},
  options:{{
    responsive:true,maintainAspectRatio:false,animation:{{onComplete:syncSaldoDI}},
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}`}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:11}},color:'#888780',maxRotation:35,minRotation:25}},border:{{display:false}}}},
      y:{{beginAtZero:true,ticks:{{stepSize:1,font:{{size:11}},color:'#888780'}},grid:{{color:'rgba(136,135,128,0.15)'}},border:{{display:false}}}}
    }}
  }},
  plugins:[{{id:'lblDiDI',afterDatasetsDraw(chart){{
    const ctx2=chart.ctx;
    chart.data.datasets.forEach((_,di)=>{{chart.getDatasetMeta(di).data.forEach((bar,i)=>{{
      const val=chart.data.datasets[di].data[i];if(val===0)return;
      ctx2.save();ctx2.font='600 10px Inter,sans-serif';ctx2.fillStyle='#fff';ctx2.textAlign='center';ctx2.textBaseline='middle';
      ctx2.fillText(val,bar.x,bar.y+bar.height/2);ctx2.restore();
    }});}});
  }}}}]
}});
function syncSaldoDI(){{
  if(!barDiDI)return;
  const meta=barDiDI.getDatasetMeta(0);const xPos=meta.data.map(b=>b.x);
  const lp=xPos[0];const rp=barDiDI.width-xPos[xPos.length-1];
  if(lineSaldoDI)lineSaldoDI.destroy();
  lineSaldoDI=new Chart(document.getElementById('lineSaldo_{_cid_di}').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[{{data:saldo,borderColor:'#e05a5a',backgroundColor:'#e05a5a',pointBackgroundColor:'#e05a5a',pointRadius:5,pointHoverRadius:7,borderWidth:2,tension:0}}]}},
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:20,left:lp,right:rp,bottom:4}}}},plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},y:{{display:false,min:0,max:{_saldo_max_di}*1.5+1}}}}}},
    plugins:[{{id:'lblSaldoDI',afterDatasetsDraw(chart){{
      const ctx2=chart.ctx;chart.getDatasetMeta(0).data.forEach((pt,i)=>{{ctx2.save();ctx2.font='600 11px Inter,sans-serif';ctx2.fillStyle='#c0392b';ctx2.textAlign='center';ctx2.fillText(saldo[i],pt.x,pt.y-10);ctx2.restore();}});
    }}}}]
  }});
}}
</script></body></html>""", height=420)

        # ── OS Fora do SLA por Responsável ────────────────────────────────
        if col_resp_di and col_resp_di in df_di.columns and len(fora_di) > 0:
            st.markdown(f'<div class="section-title">🔴 OS Fora do SLA por Responsável (> {sla_d_di} dias úteis)</div>', unsafe_allow_html=True)
            fora_grp = fora_di.groupby(col_resp_di).agg(
                OS_Fora=("Dias Uteis","count"),
                Media_Dias=("Dias Uteis","mean"),
                Max_Dias=("Dias Uteis","max")
            ).reset_index().sort_values("OS_Fora", ascending=False)
            fora_grp["Média Dias"] = fora_grp["Media_Dias"].round(1)
            fora_grp["Máx. Dias"]  = fora_grp["Max_Dias"].astype(int)
            fora_grp = fora_grp.rename(columns={col_resp_di:"Responsável","OS_Fora":"OS Fora SLA"})
            st.markdown(estilizar(fora_grp[["Responsável","OS Fora SLA","Média Dias","Máx. Dias"]]), unsafe_allow_html=True)
            st.markdown("")

        # ── Exportar Excel ────────────────────────────────────────────────
        excel_di = gerar_excel_os(df_di, sla_d_di, col_nos_di, col_resp_di, col_emp_di, col_stat_di, col_final_di)
        st.download_button(
            label="📥 Exportar Relatório Excel — Desempenho Individual",
            data=excel_di,
            file_name=f"Desempenho_Individual_{datetime.today().strftime('%d%m%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )



elif pagina == "⚙️ Configuração de Motivos":
    st.markdown('<div class="section-title">⚙️ Configuração de Motivos</div>', unsafe_allow_html=True)
    area_cfg=st.selectbox("Área",["Implantação","Tech","Produtos"])
    dic_cfg_map={"Implantação":("dic_implantacao",CLASSIFICACAO_IMPLANTACAO_PADRAO),"Tech":("dic_tech",CLASSIFICACAO_TECH_PADRAO),"Produtos":("dic_produtos",CLASSIFICACAO_PRODUTOS_PADRAO)}
    key_dic,padrao=dic_cfg_map[area_cfg]; dic_atual=st.session_state[key_dic]
    st.info("🔴 Incidente = erro, falha ou comportamento incorreto   |   🔵 Solicitação = criação, consulta, alteração ou atividade operacional")
    rows_cfg=[{"Motivo":m,"Classificação":d["tipo"] if isinstance(d,dict) else d,"SLA":d.get("sla","") if isinstance(d,dict) else ""} for m,d in sorted(dic_atual.items())]
    df_cfg=pd.DataFrame(rows_cfg)
    st.markdown(f"**{len(df_cfg)} motivos cadastrados para {area_cfg}**")
    edited=st.data_editor(df_cfg,use_container_width=True,num_rows="dynamic",
        column_config={"Motivo":st.column_config.TextColumn("Motivo",width="large"),
            "Classificação":st.column_config.SelectboxColumn("Classificação",width="medium",options=["Incidente","Solicitação","Melhoria - Solicitação de Melhoria"]),
            "SLA":st.column_config.SelectboxColumn("SLA",width="small",options=["","02:00","04:00","08:00","16:00","24:00"])},
        hide_index=True,key=f"editor_{area_cfg}")
    cs1,cs2,cs3=st.columns([1,1,2])
    with cs1:
        if st.button("💾 Salvar alterações",type="primary"):
            novo_dic={row["Motivo"]:{"tipo":row["Classificação"],"sla":row["SLA"] if row["SLA"] else None} for _,row in edited.iterrows() if str(row["Motivo"]).strip()}
            st.session_state[key_dic]=novo_dic; st.success(f"✅ {len(novo_dic)} motivos salvos para {area_cfg}!")
    with cs2:
        if st.button("↺ Restaurar padrão"):
            st.session_state[key_dic]=dict(padrao); st.success("Restaurado!"); st.rerun()
    with cs3:
        st.download_button("📤 Exportar JSON",data=json.dumps(st.session_state[key_dic],ensure_ascii=False,indent=2),
            file_name=f"classificacao_motivos_{area_cfg.lower()}.json",mime="application/json")

elif pagina == "ℹ️ Sobre":
    st.markdown('<div class="section-title">ℹ️ Sobre o programa</div>', unsafe_allow_html=True)
    st.markdown("""
**Relatórios Onboarding — Versão 3.2**

Sistema desenvolvido para análise de Chamados e Ordens de Serviço da equipe de Onboarding.

---

**🔄 Persistência de Dados**

O sistema salva automaticamente todos os dados no GitHub ao carregar qualquer planilha.
Ao reabrir o sistema ou recarregar a página, todos os dados são restaurados automaticamente.

Dados persistidos:
- Planilhas de Chamados (Implantação, Tech, Produtos) — formato Parquet
- Planilha de Ordens de Serviço — formato Parquet
- PDFs de Status Atual
- Metadados (nome do arquivo, data de carregamento)

---
Versão 3.3
    """)
