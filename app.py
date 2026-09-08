import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import os
import re
from collections import Counter
import time
# Configuración de página
st.set_page_config(page_title="Capacitación Grupo R.I. - Análisis de Accidente", page_icon="🚦", layout="wide")

DATA_FILE = "respuestas.csv"
COLUMNS_ORDER = ["timestamp", "nombre", "area", "secuencia", "controles", "causa_raiz", "que_haria", "calificacion"]

SUPABASE_CLIENT = None

def get_supabase_client():
    global SUPABASE_CLIENT
    if SUPABASE_CLIENT is not None:
        return SUPABASE_CLIENT
    
    sb_url = None
    sb_key = None
    
    try:
        if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
            sb_url = st.secrets["SUPABASE_URL"]
            sb_key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        pass
        
    if not sb_url and "SUPABASE_URL" in os.environ:
        sb_url = os.environ.get("SUPABASE_URL")
        sb_key = os.environ.get("SUPABASE_KEY", "")
        
    if sb_url and sb_key and "tu-proyecto" not in sb_url:
        try:
            from supabase import create_client
            SUPABASE_CLIENT = create_client(sb_url, sb_key)
            return SUPABASE_CLIENT
        except Exception:
            pass
    return None

def init_db():
    if not get_supabase_client():
        if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
            df = pd.DataFrame(columns=COLUMNS_ORDER)
            df.to_csv(DATA_FILE, index=False)
        else:
            try:
                df = pd.read_csv(DATA_FILE, nrows=0)
                if list(df.columns) != COLUMNS_ORDER:
                    df_full = pd.read_csv(DATA_FILE)
                    for col in COLUMNS_ORDER:
                        if col not in df_full.columns:
                            df_full[col] = "Anónimo" if col != "calificacion" else 5
                    df_full = df_full[COLUMNS_ORDER]
                    df_full.to_csv(DATA_FILE, index=False)
            except Exception:
                pass

def save_response(nombre, area, secuencia, controles, causa_raiz, que_haria, calificacion):
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = {
        "timestamp": now_str,
        "nombre": nombre.strip() if nombre and nombre.strip() else "Anónimo",
        "area": area.strip() if area and area.strip() else "Participante",
        "secuencia": secuencia.strip(),
        "controles": controles.strip(),
        "causa_raiz": causa_raiz.strip(),
        "que_haria": que_haria.strip(),
        "calificacion": calificacion
    }
    
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("respuestas").insert(new_row).execute()
            return True
        except Exception:
            pass
            
    try:
        df_new = pd.DataFrame([new_row], columns=COLUMNS_ORDER)
        df_new.to_csv(DATA_FILE, mode='a', header=not os.path.exists(DATA_FILE), index=False)
        return True
    except Exception:
        return False

def load_responses():
    sb = get_supabase_client()
    if sb:
        try:
            res = sb.table("respuestas").select("*").order("id", desc=False).execute()
            if res.data:
                df = pd.DataFrame(res.data)
                for col in COLUMNS_ORDER:
                    if col not in df.columns:
                        df[col] = "Anónimo" if col != "calificacion" else 5
                return df[COLUMNS_ORDER]
            return pd.DataFrame(columns=COLUMNS_ORDER)
        except Exception:
            pass
            
    if os.path.exists(DATA_FILE):
        try:
            return pd.read_csv(DATA_FILE)
        except Exception:
            return pd.DataFrame(columns=COLUMNS_ORDER)
    return pd.DataFrame(columns=COLUMNS_ORDER)

def is_valid_word(word):
    if not re.search(r'[aeiouáéíóú]', word):
        return False
    if len(set(word)) <= 2 and len(word) > 3:
        return False
    if not word.isalpha():
        return False
    return len(word) >= 4

def get_common_words(df, column_name, top_n=6):
    text = " ".join(df[column_name].fillna("").astype(str))
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text) 
    raw_words = text.split()
    
    stop_words = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "ante", "con", 
        "en", "para", "por", "y", "o", "u", "que", "se", "lo", "su", "sus", "al", "es", "fue", 
        "no", "si", "como", "más", "pero", "este", "esta", "ese", "esa", "porque", "qué", 
        "cuando", "donde", "quien", "son", "era", "hacer", "tiene", "tienen", "todo", "todos", 
        "muy", "me", "te", "le", "nos", "les", "ha", "han", "haya", "hay", "ya", "yo", "él", 
        "ella", "ellos", "ellas", "las", "los", "mi", "mis", "tu", "tus", "eso", "esto", 
        "cual", "cada", "sobre", "entre", "hasta", "desde", "sin", "tras", "durante", "mediante"
    }
    
    meaningful_words = [w for w in raw_words if w not in stop_words and is_valid_word(w)]
    
    if not meaningful_words:
        return pd.DataFrame()
        
    counts = Counter(meaningful_words)
    top_words = counts.most_common(top_n) 
    return pd.DataFrame(top_words, columns=["Palabra Clave", "Cantidad de Menciones"])

def get_grouped_responses(df, column_name):
    if df.empty or column_name not in df.columns:
        return []
    
    sub_df = df[df[column_name].fillna("").astype(str).str.strip().str.len() > 1].copy()
    if sub_df.empty:
        return []
        
    grouped_dict = {}
    
    for _, row in sub_df.iterrows():
        raw_text = str(row[column_name]).strip()
        # Descartar cadenas obvias de prueba como kdkfkf
        if len(set(raw_text.lower())) <= 2 and len(raw_text) > 4:
            continue
            
        norm_key = re.sub(r'\s+', ' ', raw_text.lower())
        
        # Limpiar nombre (si el usuario escribió una frase larga por error, se ignora)
        raw_name = str(row.get("nombre", "Anónimo")).strip()
        if len(raw_name) > 25 or len(raw_name) < 2 or raw_name.lower() in ["anónimo", "anonimo", "none", "nan"]:
            autor_clean = "Participante"
        else:
            autor_clean = raw_name
            
        hora_clean = str(row.get("timestamp", ""))[11:16]
        if not hora_clean:
            hora_clean = "En vivo"
            
        if norm_key not in grouped_dict:
            grouped_dict[norm_key] = {
                "display_text": raw_text.capitalize(),
                "count": 1,
                "autores": [autor_clean],
                "hora": hora_clean
            }
        else:
            grouped_dict[norm_key]["count"] += 1
            if autor_clean not in grouped_dict[norm_key]["autores"]:
                grouped_dict[norm_key]["autores"].append(autor_clean)
            grouped_dict[norm_key]["hora"] = hora_clean

    result = list(grouped_dict.values())
    result.sort(key=lambda x: x["count"], reverse=True)
    return result

def get_current_public_url():
    # 1. Si se configuró en st.secrets (Nube)
    try:
        if hasattr(st, "secrets") and "APP_URL" in st.secrets:
            url = str(st.secrets["APP_URL"]).strip()
            if url:
                return url.rstrip('/')
    except Exception:
        pass
        
    # 2. Si se configuró en variables de entorno
    if "APP_URL" in os.environ:
        url = os.environ.get("APP_URL", "").strip()
        if url:
            return url.rstrip('/')

    # 3. Si existe url.txt (despliegue local / túnel)
    if os.path.exists("url.txt"):
        try:
            with open("url.txt", "r", encoding="utf-8") as f:
                content = f.read().strip()
                match = re.search(r'https?://[^\s]+', content)
                if match:
                    return match.group(0).rstrip('/')
        except Exception:
            pass
    return ""

@st.cache_data(show_spinner=False)
def generate_qr(url):
    if not url or not url.strip():
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

init_db()

query_params = st.query_params

# ==============================================================================
# VISTA PARA EL PARTICIPANTE (CELULAR)
# ==============================================================================
if "view" in query_params and query_params["view"] == "form":
    col_logo, col_titulo = st.columns([1, 4])
    with col_logo:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=75)
    with col_titulo:
        st.title("📝 Análisis del Accidente")
        st.caption("Grupo R.I. - Capacitación de Seguridad")
        
    st.markdown("Por favor, responde con sinceridad según el caso que acabas de presenciar:")
    
    with st.form("quiz_form"):
        st.markdown("<p style='color: #94A3B8; font-size: 14px; margin-bottom: 2px;'>👤 <b>Tu Nombre o Iniciales</b> (Opcional - Déjalo en blanco si prefieres ser anónimo):</p>", unsafe_allow_html=True)
        nombre = st.text_input("Tu Nombre", placeholder="Ej. Carlos M.", label_visibility="collapsed")
        area = "Participante"
            
        st.markdown("---")
        st.markdown("##### ❓ Preguntas de Análisis")
        
        st.markdown("**1. ¿Cuál fue la secuencia de eventos que llevó al accidente?**")
        secuencia = st.text_area("Describe el orden de los hechos:", key="q1")
        
        st.markdown("**2. ¿Qué controles estaban ausentes o no fueron efectivos?**")
        controles = st.text_area("Controles fallidos o faltantes:", key="q2")
        
        st.markdown("**3. ¿Cuál considera que fue la causa raíz del accidente?**")
        causa_raiz = st.text_area("Causa principal de fondo:", key="q3")
        
        st.markdown("**4. Si mañana usted estuviera en la misma situación que la persona involucrada, ¿qué haría diferente y por qué?**")
        que_haria = st.text_area("Acción preventiva que tomarías:", key="q4")
        
        st.markdown("---")
        st.markdown("**⭐ Calificación:**")
        calificacion = st.slider("¿Qué tan enriquecedor fue este caso para tu rol?", min_value=1, max_value=5, value=5)
        
        submitted = st.form_submit_button("🚀 Enviar Respuestas")
        
        if submitted:
            if secuencia and controles and causa_raiz and que_haria:
                save_response(nombre, area, secuencia, controles, causa_raiz, que_haria, calificacion)
                st.success("✅ ¡Tus respuestas han sido registradas en vivo! Muchas gracias.")
                st.balloons()
            else:
                st.warning("⚠️ Por favor responde las 4 preguntas antes de enviar.")

# ==============================================================================
# VISTA PARA EL PRESENTADOR (MODO DIAPOSITIVAS MENTIMETER)
# ==============================================================================
else:
    # Barra lateral
    st.sidebar.markdown("### 🏢 Grupo R.I.")
    if os.path.exists("logo.png"):
        st.sidebar.image("logo.png", width=110)
        
    st.sidebar.header("⚙️ Configuración")
    public_url = st.sidebar.text_input("URL Pública:", get_current_public_url())
    form_url = f"{public_url}?view=form"
    
    # Mini QR accesible siempre por si alguien llega tarde
    with st.sidebar.expander("📱 Ver Código QR (Acceso Rápido)"):
        if public_url:
            qr_sidebar = generate_qr(form_url)
            if qr_sidebar:
                st.image(qr_sidebar, caption="Escanea para unirte")
                st.caption(f"[Abrir formulario]({form_url})")
        else:
            st.caption("⏳ Conectando túnel...")

    auto_refresh = st.sidebar.checkbox("⚡ Actualización en vivo", value=True, help="Refresca las respuestas cada 5 segundos.")

    df = load_responses()

    sb = get_supabase_client()
    if sb:
        st.sidebar.success("☁️ Almacenamiento: **Supabase (Nube)**")
    else:
        st.sidebar.caption("📁 Almacenamiento: **CSV Local**")

    # Descarga
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Reportes")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("💾 Descargar Resultados (CSV)", data=csv, file_name="respuestas_capacitacion.csv", mime="text/csv")
    else:
        st.sidebar.button("💾 Descargar Resultados (CSV)", disabled=True)

    # Reinicio
    with st.sidebar.expander("🧹 Reiniciar Capacitación"):
        st.warning("Se eliminarán las respuestas guardadas.")
        if st.button("Confirmar Borrado"):
            if sb:
                try:
                    sb.table("respuestas").delete().neq("id", 0).execute()
                except Exception:
                    pass
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            init_db()
            st.success("Tablero listo para un nuevo grupo.")
            st.rerun()

    # Control de Estado de Diapositiva
    SLIDES = [
        "📱 1. Bienvenida y Conexión QR",
        "1️⃣ 2. Secuencia de Eventos",
        "2️⃣ 3. Controles Ausentes",
        "3️⃣ 4. Causa Raíz",
        "4️⃣ 5. ¿Qué Harías Diferente?",
        "📊 6. Resumen Global y Cierre"
    ]

    if "slide_idx" not in st.session_state:
        st.session_state.slide_idx = 0

    def go_prev_slide():
        if st.session_state.slide_idx > 0:
            st.session_state.slide_idx -= 1

    def go_next_slide():
        if st.session_state.slide_idx < len(SLIDES) - 1:
            st.session_state.slide_idx += 1

    # ENCABEZADO PRINCIPAL DE LA PRESENTACIÓN
    col_top_logo, col_top_title, col_top_metric = st.columns([1, 6, 2])
    with col_top_logo:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=95)
    with col_top_title:
        st.markdown("<h2 style='margin-bottom:0px; color:#F8FAFC;'>Capacitación Interactiva: Análisis de Accidente</h2>", unsafe_allow_html=True)
        st.caption("Grupo R.I. • Modo Presentador en Vivo")
    with col_top_metric:
        total_respuestas = len(df)
        st.markdown(
            f"<div style='background: #1E293B; border-radius: 10px; padding: 10px 15px; text-align: center; border: 1px solid #334155;'>"
            f"<span style='font-size: 13px; color: #94A3B8; text-transform: uppercase;'>Participantes</span><br>"
            f"<span style='font-size: 26px; font-weight: bold; color: #38BDF8;'>🟢 {total_respuestas}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin-top: 8px; margin-bottom: 12px; border-color: #334155;'>", unsafe_allow_html=True)

    # BARRA DE NAVEGACIÓN TIPO MENTIMETER / SLIDES
    nav_col1, nav_col2, nav_col3 = st.columns([1.2, 5.5, 1.2])
    
    with nav_col1:
        st.button("⬅️ Anterior", width="stretch", disabled=(st.session_state.slide_idx == 0), on_click=go_prev_slide)

    with nav_col2:
        st.selectbox(
            "Selecciona la Diapositiva Activa:",
            options=range(len(SLIDES)),
            format_func=lambda i: SLIDES[i],
            key="slide_idx",
            label_visibility="collapsed"
        )

    with nav_col3:
        st.button("Siguiente ➡️", width="stretch", disabled=(st.session_state.slide_idx == len(SLIDES) - 1), on_click=go_next_slide)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # DIAPOSITIVA 0: BIENVENIDA Y CÓDIGO QR GIGANTE
    # ==========================================================================
    if st.session_state.slide_idx == 0:
        qr_img = generate_qr(form_url) if public_url else None
        avg_calif = f"⭐ {df['calificacion'].mean():.1f} / 5" if (not df.empty and "calificacion" in df.columns and not pd.isna(df['calificacion'].mean())) else "⭐ Pendiente"

        col_left, col_right = st.columns(2, gap="medium")

        with col_left:
            with st.container(border=True):
                st.markdown("<h2 style='text-align: center; margin-bottom: 0px;'>📱 ¡Escanea para Unirte!</h2>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #94A3B8; margin-top: 4px; font-size: 15px;'>Apunta la cámara de tu celular al código QR:</p>", unsafe_allow_html=True)
                
                if qr_img:
                    q1, q2, q3 = st.columns([1, 2.5, 1])
                    with q2:
                        st.image(qr_img, caption="Usa tus datos móviles • Sin instalar apps", width="stretch")
                    st.markdown(f"<div style='text-align: center; margin-top: 8px;'><span style='background: #0F172A; border: 1px solid #334155; padding: 6px 14px; border-radius: 8px; font-family: monospace; color: #38BDF8; font-size: 13px;'>{form_url}</span></div>", unsafe_allow_html=True)
                else:
                    st.info("🔄 Conectando túnel seguro de Cloudflare para celulares... Estará listo en un instante.")
                    time.sleep(1.5)
                    st.rerun()

        with col_right:
            with st.container(border=True):
                st.markdown("<h2 style='margin-bottom: 0px;'>📌 Dinámica de la Sesión</h2>", unsafe_allow_html=True)
                st.markdown("<p style='color: #94A3B8; margin-top: 4px; font-size: 15px;'>Pasos para participar en el análisis del caso:</p>", unsafe_allow_html=True)
                
                st.markdown("""
1. **Conéctate:** Escanea el código QR proyectado.
2. **Analiza el caso:** Responde a las 4 preguntas sobre la secuencia, controles y causa raíz.
3. **Aporta en vivo:** Tus reflexiones aparecerán reflejadas en tiempo real.
4. **Califica:** Evalúa la sesión al finalizar.
                """)
                
                st.markdown("---")
                
                m1, m2 = st.columns(2)
                with m1:
                    st.metric("Respuestas Enviadas", f"{len(df)} personas")
                with m2:
                    st.metric("Calificación Inicial", avg_calif)
                
                if len(df) > 0:
                    st.success(f"🎉 ¡Ya tenemos {len(df)} respuestas listas! Haz clic en **Siguiente ➡️** arriba para iniciar.")

    # ==========================================================================
    # DIAPOSITIVAS 1 A 4: PREGUNTAS INDIVIDUALES (ENFOQUE TOTAL)
    # ==========================================================================
    elif 1 <= st.session_state.slide_idx <= 4:
        preguntas_info = [
            {
                "num": "1",
                "col": "secuencia",
                "titulo": "¿Cuál fue la secuencia de eventos que llevó al accidente?",
                "sub": "Orden cronológico y hechos clave identificados por el equipo.",
                "color": "#38BDF8" # Cyan/Azul
            },
            {
                "num": "2",
                "col": "controles",
                "titulo": "¿Qué controles estaban ausentes o no fueron efectivos?",
                "sub": "Barreras de seguridad, procedimientos o controles fallidos.",
                "color": "#F87171" # Rojo suave
            },
            {
                "num": "3",
                "col": "causa_raiz",
                "titulo": "¿Cuál considera que fue la causa raíz del accidente?",
                "sub": "Origen fundamental del fallo según el consenso del grupo.",
                "color": "#34D399" # Verde esmeralda
            },
            {
                "num": "4",
                "col": "que_haria",
                "titulo": "¿Qué haría diferente y por qué si estuviera en esa situación?",
                "sub": "Acciones preventivas y lecciones aprendidas compartidas.",
                "color": "#FBBF24" # Amarillo/Ámbar
            }
        ]

        info = preguntas_info[st.session_state.slide_idx - 1]

        # Encabezado de la pregunta con tipografía imponente (sin sangrías HTML)
        st.markdown(
            f"<div style='background: #1E293B; border-left: 6px solid {info['color']}; padding: 18px 24px; border-radius: 12px; margin-bottom: 20px;'>"
            f"<span style='color: {info['color']}; font-weight: 700; font-size: 14px; text-transform: uppercase;'>Pregunta {info['num']} de 4</span>"
            f"<h2 style='color: #F8FAFC; margin: 4px 0 6px 0; font-size: 26px;'>{info['titulo']}</h2>"
            f"<p style='color: #94A3B8; font-size: 15px; margin: 0;'>{info['sub']}</p>"
            f"</div>",
            unsafe_allow_html=True
        )

        sub_df = df[df[info["col"]].fillna("").astype(str).str.strip().str.len() > 1].copy()
        grouped_items = get_grouped_responses(df, info["col"])

        col_left, col_right = st.columns([1, 1.8], gap="large")

        # ======================================================================
        # COLUMNA IZQUIERDA: CONTADOR Y LISTA DE PARTICIPANTES (SIN GRÁFICAS)
        # ======================================================================
        with col_left:
            with st.container(border=True):
                st.markdown("### 👥 Participación")
                total_en_esta = len(sub_df)
                st.metric(label="Personas que han respondido", value=f"{total_en_esta} participantes")
                
                st.markdown("---")
                st.markdown("##### 📋 Personas que respondieron:")
                
                if not sub_df.empty:
                    participantes = []
                    for _, r in sub_df.iterrows():
                        nom = str(r.get("nombre", "Anónimo")).strip()
                        if len(nom) > 25 or len(nom) < 2 or nom.lower() in ["anónimo", "anonimo", "none", "nan"]:
                            nom_clean = "Participante anónimo"
                        else:
                            nom_clean = nom
                        hora = str(r.get("timestamp", ""))[11:16]
                        participantes.append((nom_clean, hora))
                    
                    for nom_p, hora_p in participantes:
                        st.markdown(f"✅ **{nom_p}** `({hora_p})`")
                else:
                    st.info("Aún no hay respuestas registradas para esta pregunta.")

        # ======================================================================
        # COLUMNA DERECHA: APORTES DEL EQUIPO (TARJETAS NATIVAS)
        # ======================================================================
        with col_right:
            st.markdown(f"### 💬 Aportes del Equipo ({len(grouped_items)} ideas)")
            
            if not grouped_items:
                st.info("Esperando que los participantes envíen sus respuestas desde sus celulares...")
            else:
                for item in grouped_items:
                    with st.container(border=True):
                        if item["count"] > 1:
                            st.markdown(f":orange-background[🔥 **Coincidencia: {item['count']} personas coincidieron en esta respuesta**]")
                        
                        st.markdown(f"<p style='color: #F8FAFC; font-size: 20px; font-weight: 600; margin: 4px 0 10px 0;'>\"{item['display_text']}\"</p>", unsafe_allow_html=True)
                        
                        c_autor, c_hora = st.columns([3, 1])
                        with c_autor:
                            st.caption(f"👤 {', '.join(item['autores'][:3])}")
                        with c_hora:
                            st.caption(f"⏰ {item['hora']}")

    # ==========================================================================
    # DIAPOSITIVA 5: RESUMEN GLOBAL Y CIERRE
    # ==========================================================================
    elif st.session_state.slide_idx == 5:
        st.markdown(
            "<div style='background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); padding: 25px; border-radius: 16px; border: 1px solid #334155; text-align: center; margin-bottom: 25px;'>"
            "<h2 style='color: #F8FAFC; margin-bottom: 6px;'>🏁 Resumen Final de la Capacitación</h2>"
            "<p style='color: #94A3B8; font-size: 16px; margin: 0;'>Consolidado de resultados y lecciones aprendidas con el equipo.</p>"
            "</div>",
            unsafe_allow_html=True
        )

        c_stat1, c_stat2, c_stat3 = st.columns(3)
        with c_stat1:
            st.metric("Total de Participantes", f"{len(df)} personas")
        with c_stat2:
            if not df.empty and "calificacion" in df.columns:
                avg_score = df["calificacion"].mean()
                st.metric("Satisfacción del Caso", f"⭐ {avg_score:.2f} / 5.0")
            else:
                st.metric("Satisfacción del Caso", "N/A")
        with c_stat3:
            st.metric("Preguntas Analizadas", "4 de 4 completadas")

        st.markdown("---")
        st.markdown("### 🏆 Conclusiones Principales del Grupo")

        col_w1, col_w2, col_w3, col_w4 = st.columns(4)
        cols_titulos = [
            ("1. Secuencia", "secuencia", "#38BDF8"),
            ("2. Controles", "controles", "#F87171"),
            ("3. Causa Raíz", "causa_raiz", "#34D399"),
            ("4. Qué Haría Diferente", "que_haria", "#FBBF24"),
        ]
        target_cols = [col_w1, col_w2, col_w3, col_w4]

        for idx, (label, col_name, color) in enumerate(cols_titulos):
            with target_cols[idx]:
                with st.container(border=True):
                    st.markdown(f"<span style='color: {color}; font-weight: bold; font-size: 14px;'>{label}</span>", unsafe_allow_html=True)
                    top_items = get_grouped_responses(df, col_name)
                    if top_items:
                        best = top_items[0]
                        st.markdown(f"**\"{best['display_text']}\"**")
                        if best['count'] > 1:
                            st.caption(f"🔥 {best['count']} coincidencias")
                    else:
                        st.caption("Sin respuestas registradas")

        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
        st.success("👏 ¡Excelente sesión de capacitación! Puedes exportar el reporte completo desde el menú lateral.")

    # Auto-refresco en vivo
    if auto_refresh:
        time.sleep(5)
        st.rerun()
