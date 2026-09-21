"""Official Indonesian volcanic hazard zone (KRB) reference maps.

PVMBG (Pusat Vulkanologi dan Mitigasi Bencana Geologi) publishes a static
Kawasan Rawan Bencana map per volcano on MAGMA Indonesia. These are plain
public storage files (no session/CSRF, unlike the site's CCTV images), so
they can be linked/embedded directly as a reference image.

Source: https://magma.esdm.go.id/v1/gunung-api/peta-kawasan-rawan-bencana
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

SOURCE_URL = "https://magma.esdm.go.id/v1/gunung-api/peta-kawasan-rawan-bencana"
ATTRIBUTION = "Pusat Vulkanologi dan Mitigasi Bencana Geologi (PVMBG), Badan Geologi, Kementerian ESDM"

# (volcano name, year published, image URL). Scraped once from the source page above;
# PVMBG has no API for this, and the images are plain hotlinkable storage files.
_SEED: list[tuple[str, int, str]] = [
    ("Agung", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Xp5UaaKvPTNMxPkzd6ZPkQAQF5IyTw5OtZitmS5d.jpg"),
    ("Ambang", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/zt9SBVb0hAELeV8PL4JllkTL74ScgXJwE7Fx0qOE.jpg"),
    ("Anak Krakatau", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/gZcXl6jpyIKxuoUy5sNLEO2pGFXv3HHMHqNacuKw.jpg"),
    ("Anak Ranakah", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/gZhiVI0gFHTWrAUgUuE2v3evRRNS12dFiWaKZFKr.jpg"),
    ("Arjuno Welirang", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/nv7BzPPJtYdUM8uoWHehPyv9qnVi2RtyqZlWn674.jpg"),
    ("Awu", 2016, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/qCBaisIzHxkI9Q5mUMpKL1FClgdslMXSwkBPmSro.jpg"),
    ("Banda Api", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/fmdRe1bCXuOHc4yUpn8AUHJEAMclnq7QLyL9UNlf.jpg"),
    ("Batur", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/xJQCCgdonrsvfovMyZjxpJEtcjHUFcpl0DSeSyWW.jpg"),
    ("Batutara", 2012, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/ploto7aeA4rsWvBgaVifCxjhX3vn5kfcZGR3lA09.jpg"),
    ("Bromo", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/oMnjARI8dItEFJ5rQqBIFp3nJm48qWrOPLNPQabt.jpg"),
    ("Bur Ni Telong", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/y8shVhAWclLZ9myVQFRHkZCmzLDTkitCFqP9cYR3.jpg"),
    ("Ciremai", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Md4LPOs7BJqcAl0L7KmbIMH9xiLa6PG7W5a97MU4.jpg"),
    ("Colo", 2004, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/o97rJXvYPX1xaw5VWtydRRuB8HqYmxvEDwaocF4K.jpg"),
    ("Dempo", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/KvFe4MNA7al59Kye8Rnw6bw3U1KnFDMxYMHst7nA.jpg"),
    ("Dieng", 2011, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/02JNV19EQhhQvckbYEX8kQQ9Qdh91Od7xE4EzBtJ.jpg"),
    ("Dukono", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/dnrh2FlNqRpYTrcI2A9MovyfEWlCH03PTuHS5zVC.jpg"),
    ("Ebulobo", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/2epN0hpQ9ISqEWL081TnUr113P2ldABNtEkzzuAx.jpg"),
    ("Egon", 2005, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/RkO0i70BkkPnCmUInWmHx5TtWRaIFncs5gpQsIx3.jpg"),
    ("Galunggung", 2016, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Toe1iFZPSoUZnpPmogTbWXIu5LxsaWwNVwaSX4cQ.jpg"),
    ("Gamalama", 1996, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/zpnkYXAs2F0hNPb0zsuThek8c99VlLjiJayriIh2.jpg"),
    ("Gamkonora", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/1Ba7X6rPddtwRVKPUhV7r9ahwTTlbvsilLdoEvyd.jpg"),
    ("Gede", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/6qZAuTRzQTrp6HhQz4fUb0d5ZsqL6nmpQIiuJFs1.jpg"),
    ("Guntur", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/9VM69VpLBlajiiHVOiEUoYtyac3y5xnC3dX7ihTj.jpg"),
    ("Ibu", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/ShTymO274gJv2acx33v2f42ZOJbyxID8kyPbeJEl.jpg"),
    ("Ijen", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/cZEUcQg3npy31VnoNzGwYjA3HQan9yJ0kj5o8VJq.jpg"),
    ("Ile Werung", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/JCyXcFjwJ8AUBhntjeHD6IMdh86wh4D1NlyEQ5Yz.jpg"),
    ("Ili Boleng", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/iicGwsVr60thajENuVPgYvJKZAqrdLGVj9CQu250.jpg"),
    ("Ili Lewotolok", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/bHUucHe5NlaC8pXrdqjx9jERaZ7D7FEnVLC2zgio.jpg"),
    ("Inielika", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/mXzJkg30XCohSBiLUqOLIACHfaKRIQmkv4jveGQY.jpg"),
    ("Inierie", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/FwUs4hy5AR78PrqVxKYQdIOM62hKtWqWF85tUbjn.jpg"),
    ("Iya", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/A1ZLbjwz186uGzUSA5JMnHjCTqAdQ1d4u8cRaR3h.jpg"),
    ("Kaba", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/o2MWHIoDnuUbdBwuqwueDqsIw5mfjbPm1ys7iqsV.jpg"),
    ("Karangetang", 2011, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/tkkreoklnvg0rKZoDXpSwHXyXyyxdyU1wXxavM7g.jpg"),
    ("Kelimutu", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/prY70gDw3XCA6NPZxrjCIBGNmI6peewqspAM1Vjt.jpg"),
    ("Kelud", 2014, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/CH1H4QzQGsRxBUH1x5DwXD3L5Ekm4O7xawgmwvGy.jpg"),
    ("Kerinci", 2014, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/LDQsLeFweLqQ8EJFOgi5lS6HrYtZMvEuIDtcYKDk.jpg"),
    ("Kie Besi", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/6xVFBRhTM5pmMnnH4WAfn8rexrInwcNoQ7doekHp.jpg"),
    ("Lereboleng", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/PtbL89BKqAAbR01lK6HT9iGDiPvrF4AYRzYOrbkv.jpg"),
    ("Lewotobi Laki-laki", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/wEPzhwq0VZM5ob0bNp0lrwtXFafeYac0YjPiwNBa.jpg"),
    ("Lewotobi Perempuan", 2009, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/9DuxyydgFZM05WwCXQCOOfWU5IHWy1qR9d7E2jbm.jpg"),
    ("Lokon", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/RkDeUnwm2HIrWlWRL4bEA0eNcBYBXJwtbyudNpjb.jpg"),
    ("Mahawu", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/a7xi8pydbwqgzjtVEU39sIlLh5HALALe6iqwObfz.jpg"),
    ("Marapi", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/FHwWZbDdb69EkUhU5HysqSWLE9cqghPTcbyzMm7C.jpg"),
    ("Merapi", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/bno2urlVicsKdLgjG6WWQYMKCxAc4OuyBink8vLX.jpg"),
    ("Papandayan", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/nXWFLWtTw3YSzTmf6GvaCpqbujLmtZpOUFAmXh0I.jpg"),
    ("Peut Sague", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/a1K7nmV5NLNTbJzon6BamhjqLFnLoIQpQjzQIy5d.jpg"),
    ("Raung", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/oy6FBTzIoIWQw6sQ9R3UVAvdKg47oP04F4aksKDL.jpg"),
    ("Rinjani", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Xk7AeELLPlvnj51Bt86oIT435MbUWBuMgbStaeq9.jpg"),
    ("Rokatenda", 2013, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/kr5qMviV1N8rQkPNg3iUnQkHqHtvVFxB6sJFNEb3.jpg"),
    ("Ruang", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/d5GmZVaexkPCSdoZP9mrKLLJ6xcf8fyvLfFk1PlX.jpg"),
    ("Salak", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/QkAfabi51oFdB9pbCqMQyf7yBkvn7JnV4Jdy4xZ3.jpg"),
    ("Sangeang Api", 2016, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/wgmE9GPzAMAibUPEvuvYzAzIRqBufnSMmlS9g6p3.jpg"),
    ("Semeru", 1996, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/XCn5tGMipQBYKFC27Xrmv0aneUbppqsukXVDeb3s.jpg"),
    ("Seulawah Agam", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/DmuA537LLbLXfksx5MRgtmznVcVN7YXnhjq3rqXm.jpg"),
    ("Sinabung", 2015, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/8VAVhPXZIctSkU9pL14T8BdXKjeQXhMsqobsNz34.jpg"),
    ("Sirung", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/QyuBncxNBQ0PFCFtsTAEOLqgsv09LPSGWzbLr9v5.jpg"),
    ("Slamet", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/uX58Lk05wUlDhOZ7OiJ4O5ge18MyCAIj9ik2v3kE.jpg"),
    ("Soputan", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/kNYJNcrhiSII6WBWrw1h0dbNkRafyip0l0Fl5eJu.jpg"),
    ("Sorikmarapi", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/wFYIBbiESDhD8OttzeykajGRoZfdlDEpa8wemes3.jpg"),
    ("Sumbing", 2006, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Yiob7nEKiY4Z5bYs0qWDVtuuW9imN9xn9inC30Wy.jpg"),
    ("Sundoro", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/7aswqbvkI6n6xTaoWg8iSjKsN3AbQU4rW0XsTHsq.jpg"),
    ("Talang", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/hidsAepfiXqT0jUtnfOqLn1Exyahu49qfvbor0Dp.jpg"),
    ("Tambora", 2008, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/RGHfp4TcOd8XoxB9Z9LasJLXEmfs5FnYw3bTBIf7.jpg"),
    ("Tandikat", 2007, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/h5K3b0G3mDTmoEV9gAy5HgMrGcF9gdrt4rOHV55H.jpg"),
    ("Tangkoko", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/EMVdWYpTgVI9jkYYAH9de9JyqNMNizotVzADGxYv.jpg"),
    ("Tangkuban Parahu", 2005, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/Dkfw383kDk3b0mIYZhJvoa1z5cSg8woY3wyl3Msc.jpg"),
    ("Wurlali", 2010, "https://magma.esdm.go.id/storage/krb-gunungapi/medium/PeORaMUTWrs20XyCA0hPcGLBOJC4uhkuGmxb5PHU.jpg"),
]


@dataclass(frozen=True)
class KrbMap:
    volcano_name: str
    year: int
    image_url: str


def _normalise(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


_BY_NORMALISED_NAME: dict[str, KrbMap] = {
    # MAGMA serves the same image at several size tiers under one path; "large"
    # is legible when zoomed, "medium" is not.
    _normalise(name): KrbMap(volcano_name=name, year=year, image_url=url.replace("/medium/", "/large/"))
    for name, year, url in _SEED
}


def find_krb_map(*names: str | None) -> KrbMap | None:
    """Match a volcano name (canonical name and/or known aliases) to its KRB map.

    Tries an exact normalised match first, then falls back to substring
    containment so e.g. "Tengger Caldera" (our catalogue's canonical name for
    Bromo) can still resolve via its alias.
    """
    candidates = [_normalise(n) for n in names if n]
    for candidate in candidates:
        if candidate in _BY_NORMALISED_NAME:
            return _BY_NORMALISED_NAME[candidate]

    for candidate in candidates:
        if len(candidate) < 5:
            continue
        for key, entry in _BY_NORMALISED_NAME.items():
            if candidate in key or key in candidate:
                return entry
    return None
