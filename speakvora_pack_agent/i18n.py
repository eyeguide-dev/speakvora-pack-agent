"""Everything language-specific the agent needs besides the pack's own lines: the words people text to trigger a workflow, opt-out words, date formats, and the few glue words in a message. Covers the 12 languages Speakvora packs exist in
(en, es, fr, pt, it, de, fi, hi, ja, zh, ar, ko) and the six added after them (ru, tr, vi, pl, nl, id). English words always still work (carriers require STOP in English). The local word lists are plain and common; add your own in agent.json under "keywords": {"hours": ["..."]}."""
import datetime as dt
from zoneinfo import ZoneInfo

LANGS = ("en", "es", "fr", "pt", "it", "de", "fi", "hi", "ja", "zh", "ar", "ko", "ru", "tr", "vi", "pl", "nl", "id")
SUBSTRING = {"hi", "ja", "zh", "ar", "ko", "de", "fi", "ru", "tr", "vi", "pl"}   # no spaces between words (hi, ja, zh, ar, ko) or heavy inflection and compounds (de, fi): match inside the text

KW = {   # topic -> language -> words
    "hours": {"en": "hours open close closing", "es": "horario horarios abierto abren cierran cerrado", "fr": "horaires heures ouvert fermé ferme fermeture", "pt": "horário horario horários aberto abre fecha fechado", "it": "orari orario aperto chiuso apre chiude",
              "de": "öffnungszeiten geöffnet offen geschlossen zeiten", "fi": "aukioloajat auki kiinni aukioloaika", "hi": "समय खुले बंद घंटे", "ja": "営業時間 営業 開店 閉店", "zh": "营业时间 几点 开门 关门", "ar": "ساعات مفتوح مغلق مواعيد", "ko": "영업시간 영업 열어 닫"},
    "directions": {"en": "address where directions parking", "es": "dirección direccion dónde donde ubicación estacionamiento", "fr": "adresse où itinéraire parking stationnement", "pt": "endereço endereco onde localização estacionamento", "it": "indirizzo dove indicazioni parcheggio",
                   "de": "adresse wo anfahrt parkplatz", "fi": "osoite missä ohjeet pysäköinti", "hi": "पता कहाँ दिशा पार्किंग", "ja": "住所 場所 行き方 駐車場", "zh": "地址 在哪 位置 停车", "ar": "عنوان أين موقع موقف", "ko": "주소 위치 어디 주차"},
    "reservation": {"en": "reserve reservation book table", "es": "reservar reserva mesa cita agendar", "fr": "réserver réservation table rendez-vous", "pt": "reservar reserva mesa consulta agendar", "it": "prenotare prenotazione tavolo appuntamento",
                    "de": "reservieren reservierung tisch termin buchen", "fi": "varaa varaus pöytä aika", "hi": "बुक आरक्षण टेबल अपॉइंटमेंट", "ja": "予約 席 テーブル", "zh": "预订 预约 订位", "ar": "حجز طاولة موعد", "ko": "예약 테이블"},
    "status": {"en": "order status pickup update", "es": "pedido estado recoger actualización", "fr": "commande statut retrait mise", "pt": "pedido status retirada atualização", "it": "ordine stato ritiro aggiornamento",
               "de": "bestellung status abholung aktualisierung", "fi": "tilaus tila nouto päivitys", "hi": "ऑर्डर स्थिति अपडेट", "ja": "注文 状況 受け取り 更新", "zh": "订单 状态 取餐 更新", "ar": "طلب حالة استلام تحديث", "ko": "주문 상태 픽업 업데이트"},
    "person": {"en": "person human manager staff agent", "es": "persona humano gerente encargado agente", "fr": "personne humain responsable gérant agent", "pt": "pessoa humano gerente atendente", "it": "persona umano responsabile operatore",
               "de": "person mensch manager mitarbeiter", "fi": "henkilö ihminen esimie työntekijä", "hi": "व्यक्ति इंसान मैनेजर", "ja": "担当者 店長 スタッフ", "zh": "人工 真人 经理 客服", "ar": "شخص مدير موظف", "ko": "사람 담당자 매니저 직원"},
    "reschedule": {"en": "reschedule change cancel move book booking", "es": "cambiar cancelar reprogramar mover", "fr": "changer annuler reporter déplacer", "pt": "remarcar mudar cancelar mover", "it": "cambiare annullare spostare riprogrammare",
                   "de": "ändern absagen stornieren verschieben", "fi": "muuta peruuta siirrä", "hi": "बदलें रद्द स्थानांतरित", "ja": "変更 キャンセル 取り消し", "zh": "更改 取消 改期", "ar": "تغيير إلغاء تأجيل", "ko": "변경 취소 연기"},
    "rules": {"en": "rules visit visiting dress", "es": "reglas visita visitas vestimenta", "fr": "règles visite visites tenue", "pt": "regras visita visitas vestimenta", "it": "regole visita visite abbigliamento", "de": "regeln besuch besuche kleidung", "fi": "säännöt vierailu", "hi": "नियम मुलाकात", "ja": "規則 面会", "zh": "规则 探视", "ar": "قواعد زيارة", "ko": "규칙 면회"},
    "bail": {"en": "bail bond", "es": "fianza", "fr": "caution", "pt": "fiança", "it": "cauzione", "de": "kaution", "fi": "takuu", "hi": "जमानत", "ja": "保釈", "zh": "保释", "ar": "كفالة", "ko": "보석"},
    "hardship": {"en": "hardship cannot afford plan", "es": "dificultad pagar plan", "fr": "difficulté payer plan", "pt": "dificuldade pagar plano", "it": "difficoltà pagare piano", "de": "schwierigkeiten zahlen ratenplan", "fi": "vaikeus maksaa maksusuunnitelma", "hi": "कठिनाई भुगतान योजना", "ja": "支払い 困難 分割", "zh": "困难 付款 分期", "ar": "صعوبة دفع خطة", "ko": "어려움 결제 분할"},
}
OPT_OUT = {"en": "stop stopall unsubscribe cancel end quit", "es": "parar detener baja", "fr": "arrêt arret", "pt": "parar sair", "it": "basta annulla", "de": "stopp abmelden beenden", "fi": "lopeta", "hi": "रोकें बंद", "ja": "停止 配信停止", "zh": "退订 停止", "ar": "إيقاف توقف", "ko": "수신거부 중지"}
GLUE = {  # short words used when a message needs more than the pack's own line
    "order": {"en": "Order", "es": "Pedido", "fr": "Commande", "pt": "Pedido", "it": "Ordine", "de": "Bestellung", "fi": "Tilaus", "hi": "ऑर्डर", "ja": "ご注文", "zh": "订单", "ar": "طلب", "ko": "주문"},
    "min": {"en": "min", "es": "min", "fr": "min", "pt": "min", "it": "min", "de": "Min.", "fi": "min", "hi": "मिनट", "ja": "分", "zh": "分钟", "ar": "دقيقة", "ko": "분"},
    "auto_footer": {"en": "(This reply was sent by an automated assistant. Reply to reach a person.)", "es": "(Esta respuesta la envió un asistente automático. Responda para hablar con una persona.)", "fr": "(Cette réponse a été envoyée par un assistant automatique. Répondez pour joindre une personne.)",
                    "pt": "(Esta resposta foi enviada por um assistente automático. Responda para falar com uma pessoa.)", "it": "(Questa risposta è stata inviata da un assistente automatico. Risponda per parlare con una persona.)", "de": "(Diese Antwort wurde von einem automatischen Assistenten gesendet. Antworten Sie, um eine Person zu erreichen.)",
                    "fi": "(Tämän vastauksen lähetti automaattinen avustaja. Vastaa, jos haluat puhua ihmiselle.)", "hi": "(यह उत्तर एक स्वचालित सहायक ने भेजा है। किसी व्यक्ति से बात करने के लिए उत्तर दें।)", "ja": "（この返信は自動アシスタントが送信しました。担当者をご希望の場合は返信してください。）", "zh": "（此回复由自动助手发送。如需人工服务，请回复。）",
                    "ar": "(أُرسل هذا الرد بواسطة مساعد آلي. رُد للتحدث مع شخص.)", "ko": "(이 답변은 자동 어시스턴트가 보냈습니다. 담당자와 연결하려면 답장하세요.)"},
    "help": {"en": "Reply STOP to unsubscribe. For help, call us.", "es": "Responda STOP para darse de baja. Para ayuda, llámenos.", "fr": "Répondez STOP pour vous désabonner. Pour de l'aide, appelez-nous.", "pt": "Responda STOP para cancelar. Para ajuda, ligue para nós.",
             "it": "Risponda STOP per annullare. Per assistenza, ci chiami.", "de": "Antworten Sie STOP zum Abmelden. Für Hilfe rufen Sie uns an.", "fi": "Vastaa STOP lopettaaksesi. Soita meille, jos tarvitset apua.", "hi": "रोकने के लिए STOP लिखें। मदद के लिए हमें कॉल करें।",
             "ja": "配信停止はSTOPと返信してください。ご不明な点はお電話ください。", "zh": "回复STOP即可退订。如需帮助，请致电我们。", "ar": "رُد بـ STOP لإلغاء الاشتراك. للمساعدة اتصل بنا.", "ko": "수신을 중지하려면 STOP이라고 답장하세요. 도움이 필요하면 전화해 주세요."},
}
DAYS = {"en": "Mon Tue Wed Thu Fri Sat Sun", "es": "lun mar mié jue vie sáb dom", "fr": "lun mar mer jeu ven sam dim", "pt": "seg ter qua qui sex sáb dom", "it": "lun mar mer gio ven sab dom", "de": "Mo Di Mi Do Fr Sa So", "fi": "ma ti ke to pe la su",
        "hi": "सोम मंगल बुध गुरु शुक्र शनि रवि", "ja": "月 火 水 木 金 土 日", "zh": "周一 周二 周三 周四 周五 周六 周日", "ar": "الإثنين الثلاثاء الأربعاء الخميس الجمعة السبت الأحد", "ko": "월 화 수 목 금 토 일"}
MONTHS = {"en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec", "es": "ene feb mar abr may jun jul ago sep oct nov dic", "fr": "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.", "pt": "jan fev mar abr mai jun jul ago set out nov dez",
          "it": "gen feb mar apr mag giu lug ago set ott nov dic", "de": "Jan Feb März Apr Mai Juni Juli Aug Sep Okt Nov Dez", "fi": "tammi helmi maalis huhti touko kesä heinä elo syys loka marras joulu",
          "hi": "जन॰ फ़र॰ मार्च अप्रैल मई जून जुल॰ अग॰ सित॰ अक्तू॰ नव॰ दिस॰", "ja": "1月 2月 3月 4月 5月 6月 7月 8月 9月 10月 11月 12月", "zh": "1月 2月 3月 4月 5月 6月 7月 8月 9月 10月 11月 12月", "ar": "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر", "ko": "1월 2월 3월 4월 5월 6월 7월 8월 9월 10월 11월 12월"}


# The six languages added after the first twelve. Short plain word lists; Russian, Polish and Turkish match inside words (heavy inflection) and Vietnamese matches syllables.
_NEW = {
    "ru": {"hours": "часы время работы открыто закрыто график", "directions": "адрес где проехать парковка", "reservation": "бронь бронировать забронировать столик запись", "status": "заказ статус самовывоз обновление",
           "person": "человек менеджер сотрудник оператор", "reschedule": "перенести изменить отменить", "rules": "правила визит посещение", "bail": "залог", "hardship": "трудности платить рассрочка",
           "opt_out": "стоп отписаться отмена", "order": "Заказ", "min": "мин", "auto_footer": "(Этот ответ отправил автоматический помощник. Ответьте, чтобы связаться с человеком.)", "help": "Отправьте STOP, чтобы отписаться. Для помощи позвоните нам.",
           "days": "пн вт ср чт пт сб вс", "months": "янв фев мар апр май июн июл авг сен окт ноя дек", "yes": "да"},
    "tr": {"hours": "saat saatler açık kapalı çalışma", "directions": "adres nerede yol tarif otopark", "reservation": "rezervasyon randevu masa", "status": "sipariş durum teslim güncelleme",
           "person": "kişi insan yönetici temsilci", "reschedule": "değiştir iptal ertele", "rules": "kurallar ziyaret", "bail": "kefalet", "hardship": "zorluk ödeme taksit",
           "opt_out": "dur iptal", "order": "Sipariş", "min": "dk", "auto_footer": "(Bu yanıt otomatik bir asistan tarafından gönderildi. Bir kişiye ulaşmak için yanıtlayın.)", "help": "Abonelikten çıkmak için STOP yazın. Yardım için bizi arayın.",
           "days": "Pzt Sal Çar Per Cum Cmt Paz", "months": "Oca Şub Mar Nis May Haz Tem Ağu Eyl Eki Kas Ara", "yes": "evet"},
    "vi": {"hours": "giờ mở cửa đóng", "directions": "địa chỉ đâu đường đỗ", "reservation": "đặt bàn hẹn", "status": "đơn trạng thái nhận cập nhật",
           "person": "người quản lý nhân viên", "reschedule": "đổi hủy dời", "rules": "quy định thăm", "bail": "bảo lãnh", "hardship": "khó khăn trả góp",
           "opt_out": "dừng hủy", "order": "Đơn hàng", "min": "phút", "auto_footer": "(Tin nhắn này do trợ lý tự động gửi. Hãy trả lời để gặp nhân viên.)", "help": "Trả lời STOP để hủy đăng ký. Cần hỗ trợ, vui lòng gọi cho chúng tôi.",
           "days": "T2 T3 T4 T5 T6 T7 CN", "months": "1 2 3 4 5 6 7 8 9 10 11 12", "yes": "có"},
    "pl": {"hours": "godziny otwarte zamknięte otwarcia", "directions": "adres gdzie dojazd parking", "reservation": "rezerwacja rezerwować stolik wizyta", "status": "zamówienie status odbiór aktualizacja",
           "person": "osoba człowiek kierownik pracownik", "reschedule": "zmień anuluj przełóż", "rules": "zasady odwiedziny wizyta", "bail": "kaucja", "hardship": "trudności płatność raty",
           "opt_out": "stop anuluj wypisz", "order": "Zamówienie", "min": "min", "auto_footer": "(Tę odpowiedź wysłał automatyczny asystent. Odpowiedz, aby skontaktować się z osobą.)", "help": "Odpowiedz STOP, aby zrezygnować. W razie pomocy zadzwoń do nas.",
           "days": "pon wt śr czw pt sob niedz", "months": "sty lut mar kwi maj cze lip sie wrz paź lis gru", "yes": "tak"},
    "nl": {"hours": "openingstijden uren open dicht gesloten", "directions": "adres waar route parkeren", "reservation": "reserveren reservering tafel afspraak boeken", "status": "bestelling status afhalen update",
           "person": "persoon mens manager medewerker", "reschedule": "wijzigen annuleren verplaatsen", "rules": "regels bezoek", "bail": "borgtocht", "hardship": "moeite betalen betalingsregeling",
           "opt_out": "stop afmelden", "order": "Bestelling", "min": "min", "auto_footer": "(Dit antwoord is verstuurd door een automatische assistent. Antwoord om een medewerker te spreken.)", "help": "Antwoord STOP om je af te melden. Bel ons voor hulp.",
           "days": "ma di wo do vr za zo", "months": "jan feb mrt apr mei jun jul aug sep okt nov dec", "yes": "ja"},
    "id": {"hours": "jam buka tutup operasional", "directions": "alamat dimana arah parkir", "reservation": "reservasi pesan meja janji", "status": "pesanan status ambil pembaruan",
           "person": "orang manusia manajer staf", "reschedule": "ubah batalkan jadwal", "rules": "aturan kunjungan", "bail": "jaminan", "hardship": "kesulitan bayar cicilan",
           "opt_out": "berhenti batal", "order": "Pesanan", "min": "mnt", "auto_footer": "(Balasan ini dikirim oleh asisten otomatis. Balas untuk menghubungi petugas.)", "help": "Balas STOP untuk berhenti berlangganan. Untuk bantuan, hubungi kami.",
           "days": "Sen Sel Rab Kam Jum Sab Min", "months": "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des", "yes": "ya"},
}
for _l, _t in _NEW.items():
    for _topic in KW:
        KW[_topic][_l] = _t[_topic]
    OPT_OUT[_l] = _t["opt_out"]
    for _k in ("order", "min", "auto_footer", "help"):
        GLUE[_k][_l] = _t[_k]
    DAYS[_l], MONTHS[_l] = _t["days"], _t["months"]
YES_WORDS = "yes true 1 sí si oui sim sì ja kyllä हाँ はい 是 نعم 예 네 да evet có tak ya"


def lang_of(code):
    c = str(code or "en").lower()[:2]
    return c if c in LANGS else "en"


def words(table, topic, lang):
    row = table[topic] if isinstance(table, dict) and topic in table else table
    en, loc = row["en"].split(), row.get(lang_of(lang), "").split()
    return list(dict.fromkeys(en + loc))


def keywords(topic, lang, extra=None):
    """English words plus the language's own words for a topic ('hours', 'directions', 'reservation', 'status', 'person', 'reschedule', 'rules', 'bail', 'hardship'), plus any you add in agent.json."""
    return list(dict.fromkeys(words(KW, topic, lang) + list((extra or {}).get(topic, []))))


def opt_out_words(lang):
    return list(dict.fromkeys(OPT_OUT["en"].split() + OPT_OUT.get(lang_of(lang), "").split()))


def glue(key, lang):
    return GLUE[key].get(lang_of(lang)) or GLUE[key]["en"]


def fmt_dt(ts, tz, lang):
    """A short local date and time in the pack's language: 'Tue Oct 13, 7:00 PM' / 'mar 13 oct, 19:00' / '10月13日(火) 19:00'."""
    lang = lang_of(lang); d = dt.datetime.fromtimestamp(ts, ZoneInfo(tz)); wd = DAYS[lang].split(" ")
    wd = DAYS[lang].split(" ") if lang not in ("zh", "ar") else DAYS[lang].split(" ")
    day = wd[d.weekday()]; mon = MONTHS[lang].split(" ")[d.month - 1]
    if lang == "en":
        return f"{day} {mon} {d.day}, {d.strftime('%I:%M %p').lstrip('0')}"
    hm = d.strftime("%H:%M")
    if lang in ("ja", "zh"):
        return f"{d.month}月{d.day}日({day}) {hm}" if lang == "ja" else f"{d.month}月{d.day}日{day} {hm}"
    if lang == "ko":
        return f"{d.month}월 {d.day}일({day}) {hm}"
    if lang == "ar":
        return f"{day} {d.day} {mon}، {hm}"
    if lang == "vi":
        return f"{day} {d.day}/{d.month}, {hm}"
    if lang == "de":
        return f"{day}, {d.day}. {mon}, {hm}"
    if lang == "hi":
        return f"{day}, {d.day} {mon}, {hm}"
    return f"{day} {d.day} {mon}, {hm}"


def matches(word, text, lang):
    """Does a trigger word appear in a message? Latin scripts match whole words; Hindi, Japanese, Chinese, Arabic and Korean match anywhere in the text."""
    import re
    t = text.lower(); w = word.lower()
    if lang_of(lang) in SUBSTRING or not w.isascii() and not any(c.isalpha() and ord(c) < 0x250 for c in w):
        return w in t
    return re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", t) is not None
