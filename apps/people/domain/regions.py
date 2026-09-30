"""O'zbekiston hududlari: viloyatlar va tumanlar (shaharlar) — manzil formasidagi bog'liq tanlagichlar uchun.

- Viloyatlar — shu yerda doimiy ro'yxat.
- Tumanlar — `DISTRICTS` dan ma'lumot ko'chirish (migration) orqali `District` jadvaliga yoziladi; keyingi
  o'zgarishlar (yangi tuman, nom tuzatish) admin panel orqali qilinadi.
- Mahallalar juda ko'p va tez o'zgaradi — tayyor ro'yxat yo'q: `Mahalla` jadvaliga admin qo'shadi yoki forma
  orqali birinchi marta kiritilganda avtomatik tushadi (keyingi safar ro'yxatda chiqadi).
"""

REGIONS = (
    "Andijon viloyati",
    "Buxoro viloyati",
    "Farg'ona viloyati",
    "Jizzax viloyati",
    "Namangan viloyati",
    "Navoiy viloyati",
    "Qashqadaryo viloyati",
    "Qoraqalpog'iston Respublikasi",
    "Samarqand viloyati",
    "Sirdaryo viloyati",
    "Surxondaryo viloyati",
    "Toshkent shahri",
    "Toshkent viloyati",
    "Xorazm viloyati",
)

# Boshlang'ich ro'yxat (2026). Aniqligi admin panelda tekshirib boriladi.
DISTRICTS: dict[str, tuple[str, ...]] = {
    "Andijon viloyati": (
        "Andijon shahri", "Xonobod shahri", "Andijon tumani", "Asaka tumani", "Baliqchi tumani", "Bo'ston tumani",
        "Buloqboshi tumani", "Izboskan tumani", "Jalaquduq tumani", "Marhamat tumani", "Oltinko'l tumani",
        "Paxtaobod tumani", "Qo'rg'ontepa tumani", "Shahrixon tumani", "Ulug'nor tumani", "Xo'jaobod tumani",
    ),
    "Buxoro viloyati": (
        "Buxoro shahri", "Kogon shahri", "Buxoro tumani", "G'ijduvon tumani", "Jondor tumani", "Kogon tumani",
        "Olot tumani", "Peshku tumani", "Qorako'l tumani", "Qorovulbozor tumani", "Romitan tumani",
        "Shofirkon tumani", "Vobkent tumani",
    ),
    "Farg'ona viloyati": (
        "Farg'ona shahri", "Marg'ilon shahri", "Qo'qon shahri", "Quvasoy shahri", "Beshariq tumani",
        "Bog'dod tumani", "Buvayda tumani", "Dang'ara tumani", "Farg'ona tumani", "Furqat tumani",
        "Oltiariq tumani", "O'zbekiston tumani", "Qo'shtepa tumani", "Quva tumani", "Rishton tumani", "So'x tumani",
        "Toshloq tumani", "Uchko'prik tumani", "Yozyovon tumani",
    ),
    "Jizzax viloyati": (
        "Jizzax shahri", "Arnasoy tumani", "Baxmal tumani", "Do'stlik tumani", "Forish tumani", "G'allaorol tumani",
        "Mirzacho'l tumani", "Paxtakor tumani", "Sharof Rashidov tumani", "Yangiobod tumani", "Zafarobod tumani",
        "Zarbdor tumani", "Zomin tumani",
    ),
    "Namangan viloyati": (
        "Namangan shahri", "Chortoq tumani", "Chust tumani", "Kosonsoy tumani", "Mingbuloq tumani",
        "Namangan tumani", "Norin tumani", "Pop tumani", "To'raqo'rg'on tumani", "Uchqo'rg'on tumani",
        "Uychi tumani", "Yangiqo'rg'on tumani",
    ),
    "Navoiy viloyati": (
        "Navoiy shahri", "Zarafshon shahri", "G'ozg'on shahri", "Karmana tumani", "Konimex tumani",
        "Navbahor tumani", "Nurota tumani", "Qiziltepa tumani", "Tomdi tumani", "Uchquduq tumani",
        "Xatirchi tumani",
    ),
    "Qashqadaryo viloyati": (
        "Qarshi shahri", "Shahrisabz shahri", "Chiroqchi tumani", "Dehqonobod tumani", "G'uzor tumani",
        "Kasbi tumani", "Kitob tumani", "Koson tumani", "Ko'kdala tumani", "Mirishkor tumani", "Muborak tumani",
        "Nishon tumani", "Qamashi tumani", "Qarshi tumani", "Shahrisabz tumani", "Yakkabog' tumani",
    ),
    "Qoraqalpog'iston Respublikasi": (
        "Nukus shahri", "Amudaryo tumani", "Beruniy tumani", "Bo'zatov tumani", "Chimboy tumani",
        "Ellikqal'a tumani", "Kegeyli tumani", "Mo'ynoq tumani", "Nukus tumani", "Qanliko'l tumani",
        "Qo'ng'irot tumani", "Qorao'zak tumani", "Shumanay tumani", "Taxiatosh tumani", "Taxtako'pir tumani",
        "To'rtko'l tumani", "Xo'jayli tumani",
    ),
    "Samarqand viloyati": (
        "Samarqand shahri", "Kattaqo'rg'on shahri", "Bulung'ur tumani", "Ishtixon tumani", "Jomboy tumani",
        "Kattaqo'rg'on tumani", "Narpay tumani", "Nurobod tumani", "Oqdaryo tumani", "Pastdarg'om tumani",
        "Paxtachi tumani", "Payariq tumani", "Qo'shrabot tumani", "Samarqand tumani", "Toyloq tumani",
        "Urgut tumani",
    ),
    "Sirdaryo viloyati": (
        "Guliston shahri", "Shirin shahri", "Yangiyer shahri", "Boyovut tumani", "Guliston tumani",
        "Mirzaobod tumani", "Oqoltin tumani", "Sardoba tumani", "Sayxunobod tumani", "Sirdaryo tumani",
        "Xovos tumani",
    ),
    "Surxondaryo viloyati": (
        "Termiz shahri", "Angor tumani", "Bandixon tumani", "Boysun tumani", "Denov tumani", "Jarqo'rg'on tumani",
        "Muzrabot tumani", "Oltinsoy tumani", "Qiziriq tumani", "Qumqo'rg'on tumani", "Sariosiyo tumani",
        "Sherobod tumani", "Sho'rchi tumani", "Termiz tumani", "Uzun tumani",
    ),
    "Toshkent shahri": (
        "Bektemir tumani", "Chilonzor tumani", "Mirobod tumani", "Mirzo Ulug'bek tumani", "Olmazor tumani",
        "Sergeli tumani", "Shayxontohur tumani", "Uchtepa tumani", "Yakkasaroy tumani", "Yangihayot tumani",
        "Yashnobod tumani", "Yunusobod tumani",
    ),
    "Toshkent viloyati": (
        "Nurafshon shahri", "Angren shahri", "Bekobod shahri", "Chirchiq shahri", "Olmaliq shahri",
        "Ohangaron shahri", "Yangiyo'l shahri", "Bekobod tumani", "Bo'ka tumani", "Bo'stonliq tumani",
        "Chinoz tumani", "Ohangaron tumani", "Oqqo'rg'on tumani", "O'rta Chirchiq tumani", "Parkent tumani",
        "Piskent tumani", "Qibray tumani", "Quyi Chirchiq tumani", "Toshkent tumani", "Yangiyo'l tumani",
        "Yuqori Chirchiq tumani", "Zangiota tumani",
    ),
    "Xorazm viloyati": (
        "Urganch shahri", "Xiva shahri", "Bog'ot tumani", "Gurlan tumani", "Hazorasp tumani", "Qo'shko'pir tumani",
        "Shovot tumani", "Tuproqqal'a tumani", "Urganch tumani", "Xiva tumani", "Xonqa tumani",
        "Yangiariq tumani", "Yangibozor tumani",
    ),
}


def region_choices(current: str = "") -> list[tuple[str, str]]:
    """Tanlagich variantlari. Ro'yxatda yo'q eski qiymat ham yo'qolmasin — u ham ko'rsatiladi."""
    choices = [("", "— Tanlang —"), *((r, r) for r in REGIONS)]
    if current and current not in REGIONS:
        choices.append((current, current))
    return choices
