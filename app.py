import json
import os
import random
import re
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from groq import Groq


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL_NAME = "openai/gpt-oss-120b"
TEMPERATURE = 0.2

HISTORY_DIR = Path("chat_history")
HISTORY_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = """
Kamu adalah AI Travel Assistant khusus untuk memberikan rekomendasi
destinasi wisata liburan di Jawa Timur, Indonesia.

ATURAN UTAMA:

1. Berikan informasi yang faktual dan relevan mengenai destinasi
   wisata di Jawa Timur.
2. Jangan mengarang atau membuat informasi yang tidak diketahui.
3. Jangan membuat nama destinasi wisata fiktif.
4. Jangan mengarang harga tiket, jam buka, alamat, fasilitas,
   jarak, waktu tempuh, rating, atau informasi lainnya.
5. Jika informasi yang diminta tidak tersedia dalam data atau konteks,
   katakan bahwa informasi tersebut tidak tersedia.
6. Jangan menebak informasi yang tidak diketahui.
7. Jika pengguna meminta rekomendasi, berikan rekomendasi berdasarkan
   informasi yang tersedia.
8. Jelaskan alasan rekomendasi berdasarkan karakteristik destinasi,
   bukan berdasarkan fakta yang dibuat-buat.
9. Fokus hanya pada destinasi wisata di Jawa Timur.
10. Jika pertanyaan tidak berkaitan dengan wisata Jawa Timur,
    jelaskan bahwa chatbot berfokus pada wisata Jawa Timur.
11. Jika terdapat informasi yang tidak cukup untuk memberikan
    rekomendasi, tanyakan informasi tambahan kepada pengguna.
12. Gunakan bahasa Indonesia yang jelas, singkat, ramah,
    dan mudah dipahami.


ATURAN ANTI-HALUSINASI:

- Jika tidak yakin terhadap suatu fakta, jangan menyatakan fakta
  tersebut sebagai kebenaran.
- Jangan mengisi informasi yang kosong dengan asumsi.
- Jangan membuat angka atau data.
- Jangan mengatakan suatu destinasi memiliki fasilitas tertentu
  jika fasilitas tersebut tidak diketahui.
- Jangan mengatakan suatu destinasi buka pada jam tertentu
  jika jam buka tidak diketahui.
- Jangan memberikan harga tiket jika harga tidak tersedia.
- Jangan membuat rating atau ulasan wisata.
- Jangan membuat alamat atau lokasi secara sembarangan.
- Jika data tidak tersedia, gunakan kalimat:
  "Maaf, informasi tersebut tidak tersedia dalam data saya."


FORMAT REKOMENDASI:

Jika pengguna meminta rekomendasi destinasi, berikan informasi
dengan format berikut jika datanya tersedia:

- Nama destinasi
- Lokasi
- Jenis wisata
- Alasan rekomendasi
- Informasi tambahan yang tersedia


BATASAN TOPIK:

Jika pengguna memberikan pertanyaan di luar topik wisata Jawa Timur,
berikan respons singkat dan arahkan pengguna kembali ke topik
wisata Jawa Timur.


ATURAN JAWABAN:

- Gunakan Bahasa Indonesia.
- Jawaban harus relevan dengan pertanyaan pengguna.
- Jangan terlalu panjang jika pertanyaan sederhana.
- Jangan mengulang pertanyaan pengguna.
- Jika informasi tidak tersedia, katakan dengan jujur.
- Gunakan format Markdown biasa saja (bullet "-", **tebal**, baris baru).
- JANGAN PERNAH menuliskan tag HTML seperti <br>, <b>, <p>, <div>,
  atau tag HTML lainnya di dalam jawaban. Untuk baris baru, cukup
  tekan enter/baris baru biasa, bukan menuliskan tag apa pun.
"""

_BR_PATTERN = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def clean_answer(text: str) -> str:
    """Ganti tag <br> dengan baris baru, buang sisa tag HTML lain."""
    text = _BR_PATTERN.sub("\n", text)
    text = _TAG_PATTERN.sub("", text)
    return text


def list_conversations():
    """Ambil semua percakapan tersimpan, terbaru di atas."""
    conversations = []

    for path in HISTORY_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                conversations.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue

    conversations.sort(
        key=lambda c: c.get("updated_at", ""),
        reverse=True,
    )

    return conversations


def save_conversation(chat_id, messages):
    """Simpan percakapan ke file JSON (tanpa system prompt)."""
    visible = [m for m in messages if m["role"] != "system"]

    if not visible:
        return

    title = visible[0]["content"].strip().replace("\n", " ")

    if len(title) > 40:
        title = title[:40].rstrip() + "..."

    data = {
        "id": chat_id,
        "title": title,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "messages": visible,
    }

    with open(HISTORY_DIR / f"{chat_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_conversation(chat_id):
    """Hapus satu percakapan tersimpan."""
    try:
        (HISTORY_DIR / f"{chat_id}.json").unlink()
    except OSError:
        pass


st.set_page_config(
    page_title="Sobat Dolan",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="expanded",
)


if not GROQ_API_KEY:
    st.error(
        "GROQ_API_KEY tidak ditemukan. "
        "Pastikan file .env sudah berisi GROQ_API_KEY."
    )
    st.stop()


client = Groq(api_key=GROQ_API_KEY)


st.markdown(
    """
    <style>

    /* ---------- GLOBAL ---------- */

    .stApp {
        background: linear-gradient(
            135deg,
            #f5fcf8 0%,
            #eefaf7 45%,
            #f7fcfb 100%
        );
    }

    .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 7rem;
    }


    /* ---------- SIDEBAR ---------- */

    section[data-testid="stSidebar"] {
        background: linear-gradient(
            180deg,
            #e8f7f1 0%,
            #edf9f5 55%,
            #f5fcfa 100%
        );
        border-right: 1px solid #d6eee5;
    }


    /* ---------- LOGO ---------- */

    .brand {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
    }

    .brand-icon {
        width: 46px;
        height: 46px;
        border-radius: 15px;
        background: linear-gradient(135deg, #58b89a, #2d9c82);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 25px;
        box-shadow: 0 8px 20px rgba(45, 156, 130, 0.20);
    }

    .brand-title {
        font-size: 21px;
        font-weight: 700;
        color: #245b4e;
        line-height: 1.1;
    }

    .brand-subtitle {
        font-size: 12px;
        color: #6b9187;
        margin-top: 3px;
    }


    /* ---------- SIDEBAR SECTION ---------- */

    .sidebar-section {
        margin-top: 24px;
        margin-bottom: 6px;
        font-size: 11px;
        font-weight: 700;
        color: #70988e;
        text-transform: uppercase;
        letter-spacing: 1px;
    }


    /* ---------- INFO CARD ---------- */

    .info-card {
        padding: 15px;
        background: rgba(255, 255, 255, 0.75);
        border: 1px solid #d7eee6;
        border-radius: 16px;
        margin-top: 12px;
        box-shadow: 0 5px 20px rgba(42, 117, 98, 0.05);
    }

    .info-title {
        font-size: 14px;
        font-weight: 700;
        color: #356b5e;
        margin-bottom: 5px;
    }

    .info-text {
        font-size: 12px;
        line-height: 1.6;
        color: #729188;
    }


    /* ---------- BUTTONS ---------- */

    .stButton > button {
        width: 100%;
        border-radius: 12px;
        border: 1px solid #d5ebe4;
        background: rgba(255, 255, 255, 0.75);
        color: #3b6f62;
        font-weight: 600;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        border-color: #78bea9;
        background: #f4fffb;
        color: #267762;
    }


    /* ---------- RIWAYAT SIDEBAR ---------- */

    section[data-testid="stSidebar"] .stButton > button {
        text-align: left;
        justify-content: flex-start;
        font-weight: 500;
        font-size: 13px;
        padding: 8px 12px;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }

    section[data-testid="stSidebar"]
    div[data-testid="stHorizontalBlock"] {
        gap: 6px;
        margin-bottom: 4px;
    }

    .history-empty {
        font-size: 12px;
        color: #8fa9a2;
        padding: 6px 2px;
    }


    /* ---------- HERO ---------- */

    .hero {
        text-align: center;
        padding: 20px 0 24px 0;
    }

    .hero-icon {
        width: 70px;
        height: 70px;
        margin: 0 auto 18px auto;
        border-radius: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 38px;
        background: linear-gradient(135deg, #d9f5eb, #c7eee3);
        box-shadow: 0 12px 35px rgba(54, 150, 126, 0.12);
    }

    .hero-title {
        font-size: 36px;
        font-weight: 700;
        color: #285e51;
        letter-spacing: -1px;
        margin-bottom: 8px;
    }

    .hero-subtitle {
        font-size: 15px;
        color: #78968e;
        max-width: 570px;
        margin: auto;
        line-height: 1.7;
    }

    .quick-title {
        text-align: center;
        color: #78968e;
        font-size: 13px;
        margin: 10px 0 14px 0;
    }


    /* ---------- CHAT ---------- */

    div[data-testid="stChatMessage"] {
        border-radius: 18px;
        padding: 6px 10px;
        margin-bottom: 10px;
        background: rgba(255, 255, 255, 0.6);
    }

    div[data-testid="stChatInput"] textarea {
        border-radius: 18px !important;
    }


    /* ---------- FOOTER ---------- */

    .footer {
        text-align: center;
        color: #91aaa3;
        font-size: 11px;
        margin-top: 25px;
    }


    /* ---------- HIDE STREAMLIT ELEMENTS ---------- */

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { background: transparent !important; }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

if "chat_started" not in st.session_state:
    st.session_state.chat_started = False

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

if "chat_id" not in st.session_state:
    st.session_state.chat_id = str(uuid.uuid4())

if "notice" not in st.session_state:
    st.session_state.notice = None

if "ended" not in st.session_state:
    st.session_state.ended = False


QUICK_PROMPTS = {
    "alam": (
        "🏔️ Wisata Alam",
        "Rekomendasikan wisata alam di Jawa Timur.",
    ),
    "pantai": (
        "🏖️ Wisata Pantai",
        "Rekomendasikan destinasi wisata pantai di Jawa Timur.",
    ),
    "keluarga": (
        "👨‍👩‍👧 Wisata Keluarga",
        "Rekomendasikan destinasi wisata di Jawa Timur "
        "yang cocok untuk liburan bersama keluarga.",
    ),
    "gunung": (
        "🌄 Wisata Pegunungan",
        "Rekomendasikan wisata pegunungan di Jawa Timur.",
    ),
}


def trigger_prompt(prompt: str) -> None:
    """Simpan prompt cepat lalu tandai chat sudah dimulai."""
    st.session_state.pending_prompt = prompt
    st.session_state.chat_started = True


def new_chat() -> None:
    """Mulai percakapan baru (yang lama sudah tersimpan otomatis)."""
    st.session_state.chat_id = str(uuid.uuid4())
    st.session_state.messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    st.session_state.chat_started = False
    st.session_state.pending_prompt = None


def open_chat(conversation) -> None:
    """Buka kembali percakapan yang tersimpan."""
    st.session_state.chat_id = conversation["id"]
    st.session_state.messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation["messages"]
    )
    st.session_state.chat_started = True
    st.session_state.pending_prompt = None


def remove_chat(chat_id: str) -> None:
    """Hapus percakapan; jika sedang dibuka, mulai chat baru."""
    delete_conversation(chat_id)

    if st.session_state.chat_id == chat_id:
        new_chat()


SYSTEM_PROMPT = """
**Panduan Penggunaan Sobat Dolan**

Aku adalah AI Travel Assistant yang fokus membantu kamu menemukan
destinasi wisata di **Jawa Timur**.

**Kamu bisa bertanya seputar:**
- Rekomendasi destinasi wisata alam, pantai, pegunungan, atau
  wisata keluarga di Jawa Timur.
- Karakteristik atau suasana suatu destinasi (misalnya "tempat
  yang cocok untuk healing" atau "wisata yang ramai spot foto").
- Perbandingan singkat antar destinasi berdasarkan jenis wisatanya.
- Ide susunan itinerary sederhana berdasarkan tema liburan.

**Jenis jawaban yang bisa aku berikan:**
- Nama destinasi, lokasi, jenis wisata, dan alasan rekomendasi
  berdasarkan karakteristiknya.
- Info tambahan **hanya jika aku benar-benar mengetahuinya** —
  aku tidak akan mengarang harga tiket, jam buka, rating, atau
  fasilitas yang tidak pasti.

**Di luar topik itu** (misalnya wisata luar Jawa Timur, resep
masakan, atau hal umum lain), aku akan mengarahkanmu kembali ke
topik wisata Jawa Timur.

Ketik `/help` kapan saja untuk melihat panduan ini lagi, atau lihat
perintah lain di kartu **⌨️ Perintah** pada sidebar.
"""


# Fakta-fakta yang relatif jarang diketahui tentang destinasi
# wisata di Jawa Timur, dipakai oleh perintah /funfact.
DESTINATION_FACTS = [
    (
        "Kawah Ijen, Banyuwangi",
        "Fenomena 'api biru' di Kawah Ijen bukan berasal dari lava, "
        "melainkan gas belerang bersuhu tinggi yang terbakar saat "
        "bersentuhan dengan udara. Fenomena ini hanya bisa disaksikan "
        "jelas pada malam hari dan termasuk salah satu dari sedikit "
        "tempat di dunia yang memilikinya.",
    ),
    (
        "Gunung Bromo, Probolinggo",
        "Hamparan pasir luas yang mengelilingi kawah Gunung Bromo "
        "memiliki nama khusus, yaitu 'Segara Wedi' atau 'Laut Pasir', "
        "karena masyarakat Tengger memaknainya seperti lautan yang "
        "terbentuk dari pasir.",
    ),
    (
        "Taman Nasional Baluran, Situbondo",
        "Taman Nasional Baluran dijuluki 'Little Africa of Java' "
        "karena kawasan savananya yang luas menyerupai lanskap padang "
        "rumput Afrika, lengkap dengan satwa liar seperti banteng dan "
        "rusa yang bisa terlihat dari kejauhan.",
    ),
    (
        "Air Terjun Madakaripura, Probolinggo",
        "Air Terjun Madakaripura dipercaya masyarakat setempat sebagai "
        "lokasi pertapaan terakhir Mahapatih Gajah Mada dari Kerajaan "
        "Majapahit, sehingga tempat ini juga punya nilai sejarah, "
        "bukan sekadar keindahan alam.",
    ),
    (
        "Situs Trowulan, Mojokerto",
        "Trowulan diyakini merupakan bekas pusat ibu kota Kerajaan "
        "Majapahit, salah satu kerajaan terbesar dalam sejarah "
        "Nusantara, dan kini menjadi kawasan situs arkeologi dengan "
        "berbagai peninggalan candi serta museum.",
    ),
    (
        "Pulau Merah, Banyuwangi",
        "Nama 'Pulau Merah' berasal dari warna tanah pada bukit kecil "
        "di pesisir pantai yang tampak kemerahan saat terkena sinar "
        "matahari, bukan karena warna pasir pantainya yang sebenarnya "
        "berwarna cokelat keemasan.",
    ),
    (
        "Kampung Warna-Warni Jodipan, Malang",
        "Kampung Warna-Warni Jodipan awalnya merupakan permukiman "
        "padat di bantaran sungai yang dianggap kumuh, sebelum "
        "diubah menjadi destinasi wisata ikonik lewat inisiatif "
        "mahasiswa dan warga setempat yang mengecat rumah-rumah "
        "dengan warna-warni cerah.",
    ),
    (
        "Gua Gong, Pacitan",
        "Gua Gong dikenal sebagai salah satu gua dengan ornamen "
        "stalaktit dan stalagmit terindah di Asia Tenggara, lengkap "
        "dengan beberapa ruangan yang diberi nama berdasarkan bentuk "
        "batuannya.",
    ),
]


def handle_command(text: str) -> bool:
    """Jalankan perintah khusus. Return True jika teks adalah perintah."""

    command = text.strip().lower()

    if command in ("/help", "/bantuan"):
        st.session_state.notice = ("info", SYSTEM_PROMPT)

    elif command in ("/clear", "/reset"):
        new_chat()
        st.session_state.notice = (
            "success",
            "Percakapan direset. Silakan mulai pertanyaan baru.",
        )

    elif command in ("/funfact", "/fakta"):
        destination, fact = random.choice(DESTINATION_FACTS)
        st.session_state.notice = (
            "info",
            f"**🧭 Tahukah kamu? — {destination}**\n\n{fact}",
        )

    elif command in ("/delete"):
        remove_chat(st.session_state.chat_id)
        st.session_state.notice = (
            "success",
            "Percakapan ini sudah dihapus.",
        )

    elif command in ("/exit", "/keluar"):
        save_conversation(
            st.session_state.chat_id,
            st.session_state.messages,
        )
        st.session_state.ended = True

    else:
        return False

    return True


with st.sidebar:

    st.markdown(
        """
        <div class="brand">
            <div class="brand-icon">🌿</div>
            <div>
                <div class="brand-title">Sobat Dolan</div>
                <div class="brand-subtitle">Travel Assistant</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="sidebar-section">Percakapan</div>',
        unsafe_allow_html=True,
    )

    st.button(
        "+  Chat Baru",
        key="btn_new",
        use_container_width=True,
        on_click=new_chat,
    )

    st.markdown(
        '<div class="sidebar-section">Riwayat</div>',
        unsafe_allow_html=True,
    )

    conversations = list_conversations()

    if not conversations:
        st.markdown(
            '<div class="history-empty">Belum ada percakapan '
            'tersimpan.</div>',
            unsafe_allow_html=True,
        )

    for conversation in conversations:

        is_active = conversation["id"] == st.session_state.chat_id

        col_open, col_del = st.columns([6, 1], gap="small")

        with col_open:
            st.button(
                ("🟢  " if is_active else "💬  ") + conversation["title"],
                key=f"open_{conversation['id']}",
                use_container_width=True,
                on_click=open_chat,
                args=(conversation,),
            )

        with col_del:
            st.button(
                "🗑️",
                key=f"del_{conversation['id']}",
                help="Hapus percakapan ini",
                use_container_width=True,
                on_click=remove_chat,
                args=(conversation["id"],),
            )

    st.markdown(
        '<div class="sidebar-section">Tentang</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="info-card">
            <div class="info-title">🌱 Jelajah Jawa Timur</div>
            <div class="info-text">
                Temukan inspirasi destinasi wisata di Jawa Timur
                sesuai kebutuhan perjalananmu.
            </div>
        </div>

        <div class="info-card">
            <div class="info-title">⌨️ Perintah</div>
            <div class="info-text">
                <code>/help</code> · panduan penggunaan<br>
                <code>/reset</code> · mulai ulang percakapan<br>
                <code>/funfact</code> · fakta unik destinasi<br>
                <code>/delete</code> · hapus chat ini<br>
                <code>/exit</code> · akhiri sesi
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if st.session_state.ended:

    st.markdown(
        """
        <div class="hero">
            <div class="hero-icon">👋</div>
            <div class="hero-title">Sampai jumpa!</div>
            <div class="hero-subtitle">
                Sesi chat sudah diakhiri dan percakapanmu tersimpan
                di riwayat. Semoga liburanmu di Jawa Timur
                menyenangkan.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_mid, col_r = st.columns([1, 2, 1])

    with col_mid:
        if st.button("🌿  Mulai Sesi Baru", use_container_width=True):
            st.session_state.ended = False
            new_chat()
            st.rerun()

    st.stop()

if not st.session_state.chat_started:

    st.markdown(
        """
        <div class="hero">
            <div class="hero-icon">🌿</div>
            <div class="hero-title">Sobat Dolan</div>
            <div class="hero-subtitle">
                Temukan destinasi wisata yang sesuai dengan suasana
                dan kebutuhan perjalananmu. Ceritakan rencana
                liburanmu, dan mari cari inspirasinya bersama.
            </div>
        </div>

        <div class="quick-title">Mulai dari pilihan berikut</div>
        """,
        unsafe_allow_html=True,
    )

    hero_keys = ["alam", "pantai", "keluarga", "gunung"]
    cols = st.columns(len(hero_keys))

    for col, key in zip(cols, hero_keys):
        label, prompt = QUICK_PROMPTS[key]
        with col:
            st.button(
                label,
                key=f"hero_{key}",
                use_container_width=True,
                on_click=trigger_prompt,
                args=(prompt,),
            )


for message in st.session_state.messages:

    if message["role"] == "system":
        continue

    with st.chat_message(message["role"]):
        st.markdown(clean_answer(message["content"]))


notice = st.session_state.notice
st.session_state.notice = None

if notice:
    level, text = notice

    if level == "success":
        st.success(text)
    else:
        st.info(text)


typed_input = st.chat_input(
    "Mau liburan ke mana hari ini?  (ketik /help untuk perintah)"
)

pending_prompt = st.session_state.pending_prompt
st.session_state.pending_prompt = None

user_input = typed_input or pending_prompt

if user_input and user_input.strip().startswith("/"):

    if handle_command(user_input):
        st.rerun()

    else:
        st.session_state.notice = (
            "info",
            f"Perintah `{user_input.strip()}` tidak dikenali. "
            "Ketik `/help` untuk melihat daftar perintah.",
        )
        st.rerun()

    user_input = None


if user_input:

    st.session_state.chat_started = True

    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):

        response_placeholder = st.empty()
        full_answer = ""

        try:
            stream = client.chat.completions.create(
                model=MODEL_NAME,
                messages=st.session_state.messages,
                temperature=TEMPERATURE,
                stream=True,
            )

            for chunk in stream:

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta.content

                if delta is None:
                    continue

                full_answer += delta
                response_placeholder.markdown(full_answer + "▌")

            full_answer = clean_answer(full_answer)
            response_placeholder.markdown(full_answer)

            st.session_state.messages.append(
                {"role": "assistant", "content": full_answer}
            )

            save_conversation(
                st.session_state.chat_id,
                st.session_state.messages,
            )

            st.rerun()

        except Exception as e:

            response_placeholder.error(
                "Maaf, terjadi kesalahan saat menghubungi AI. "
                "Silakan coba lagi."
            )

            st.session_state.messages.pop()

            print(f"Groq Error: {e}")


st.markdown(
    """
    <div class="footer">
        🌿 Sobat Dolan · Travel Assistant
        <br>
        Temukan inspirasi perjalananmu di Jawa Timur
    </div>
    """,
    unsafe_allow_html=True,
)