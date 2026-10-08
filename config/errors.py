class RuleError(ValueError):
    """Kural ihlali (oy hakkı yok, oylama kapalı, hız sınırı…): mesajı kullanıcıya gösterilir (site: bildirim,
    API: 400). Görünümler yalnızca bunu yakalar: beklenmeyen bir ValueError programlama hatasıdır, 500 olarak
    kayda düşer ve iç mesajı kullanıcıya sızmaz. Bağımlılığı yok: modeller de import edebilir.
    """
