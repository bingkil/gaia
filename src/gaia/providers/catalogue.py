"""Volcano catalogue.

A seed list of frequently active and historically significant volcanoes, used
to correlate thermal anomalies and to resolve volcano identity in advisories.

Coordinates are summit positions to roughly two decimal places. Elevations are
deliberately omitted rather than approximated; nothing in the engine uses them.
Replace this seed with a Smithsonian GVP import when a licensed copy is
available — ``VolcanoRepo.upsert_many`` is the only integration point.
"""

from __future__ import annotations

from ..domain.models import Volcano

# (name, latitude, longitude, country, aliases)
_SEED: list[tuple[str, float, float, str, tuple[str, ...]]] = [
    # Indonesia
    ("Merapi", -7.54, 110.44, "Indonesia", ()),
    ("Semeru", -8.11, 112.92, "Indonesia", ()),
    ("Anak Krakatau", -6.10, 105.42, "Indonesia", ("Krakatau", "Krakatoa")),
    ("Sinabung", 3.17, 98.39, "Indonesia", ()),
    ("Agung", -8.34, 115.51, "Indonesia", ()),
    ("Raung", -8.13, 114.04, "Indonesia", ()),
    ("Kelud", -7.93, 112.31, "Indonesia", ("Kelut",)),
    ("Tengger Caldera", -7.94, 112.95, "Indonesia", ("Bromo",)),
    ("Ili Lewotolok", -8.27, 123.51, "Indonesia", ()),
    ("Lewotobi", -8.54, 122.78, "Indonesia", ("Lewotobi Laki-laki",)),
    ("Marapi", -0.38, 100.47, "Indonesia", ()),
    ("Ibu", 1.49, 127.63, "Indonesia", ()),
    ("Dukono", 1.69, 127.89, "Indonesia", ()),
    ("Ruang", 2.30, 125.37, "Indonesia", ()),
    ("Karangetang", 2.78, 125.41, "Indonesia", ()),
    ("Soputan", 1.11, 124.73, "Indonesia", ()),
    ("Lokon-Empung", 1.36, 124.79, "Indonesia", ()),
    ("Gamalama", 0.80, 127.33, "Indonesia", ()),
    ("Kerinci", -1.70, 101.26, "Indonesia", ()),
    ("Sangeang Api", -8.20, 119.07, "Indonesia", ()),
    ("Rinjani", -8.42, 116.47, "Indonesia", ()),
    ("Slamet", -7.24, 109.21, "Indonesia", ()),
    ("Tangkuban Parahu", -6.77, 107.60, "Indonesia", ()),
    # Philippines
    ("Kanlaon", 10.41, 123.13, "Philippines", ("Canlaon",)),
    ("Mayon", 13.26, 123.69, "Philippines", ()),
    ("Taal", 14.00, 120.99, "Philippines", ()),
    ("Pinatubo", 15.13, 120.35, "Philippines", ()),
    ("Bulusan", 12.77, 124.05, "Philippines", ()),
    # Japan
    ("Fuji", 35.36, 138.73, "Japan", ("Fujisan",)),
    ("Sakurajima", 31.59, 130.66, "Japan", ("Aira",)),
    ("Aso", 32.88, 131.10, "Japan", ("Asosan",)),
    ("Suwanosejima", 29.64, 129.71, "Japan", ()),
    ("Kirishima", 31.91, 130.88, "Japan", ("Shinmoedake",)),
    ("Nishinoshima", 27.24, 140.87, "Japan", ()),
    # Kamchatka and Kurils
    ("Klyuchevskoy", 56.06, 160.64, "Russia", ("Kliuchevskoi",)),
    ("Bezymianny", 55.97, 160.59, "Russia", ()),
    ("Shiveluch", 56.65, 161.36, "Russia", ("Sheveluch",)),
    ("Karymsky", 54.05, 159.44, "Russia", ()),
    ("Ebeko", 50.69, 156.01, "Russia", ()),
    # Alaska and Cascades
    ("Redoubt", 60.49, -152.74, "United States", ()),
    ("Augustine", 59.36, -153.43, "United States", ()),
    ("Bogoslof", 53.93, -168.03, "United States", ()),
    ("Great Sitkin", 52.08, -176.13, "United States", ()),
    ("Pavlof", 55.42, -161.89, "United States", ()),
    ("Cleveland", 52.83, -169.94, "United States", ()),
    ("Shishaldin", 54.76, -163.97, "United States", ()),
    ("Mount St. Helens", 46.20, -122.18, "United States", ("St Helens",)),
    ("Rainier", 46.85, -121.76, "United States", ()),
    ("Shasta", 41.41, -122.19, "United States", ()),
    ("Yellowstone", 44.43, -110.67, "United States", ()),
    # Hawaii
    ("Kilauea", 19.42, -155.29, "United States", ()),
    ("Mauna Loa", 19.48, -155.61, "United States", ()),
    # Mexico and Central America
    ("Popocatepetl", 19.02, -98.62, "Mexico", ("Popocatépetl",)),
    ("Colima", 19.51, -103.62, "Mexico", ("Fuego de Colima",)),
    ("Fuego", 14.47, -90.88, "Guatemala", ()),
    ("Santa Maria", 14.76, -91.55, "Guatemala", ("Santiaguito",)),
    ("Pacaya", 14.38, -90.60, "Guatemala", ()),
    ("Masaya", 11.98, -86.16, "Nicaragua", ()),
    ("Telica", 12.60, -86.85, "Nicaragua", ()),
    ("Arenal", 10.46, -84.70, "Costa Rica", ()),
    ("Poas", 10.20, -84.23, "Costa Rica", ("Poás",)),
    ("Turrialba", 10.03, -83.77, "Costa Rica", ()),
    ("Rincon de la Vieja", 10.83, -85.32, "Costa Rica", ()),
    # South America
    ("Nevado del Ruiz", 4.89, -75.32, "Colombia", ()),
    ("Galeras", 1.22, -77.37, "Colombia", ()),
    ("Purace", 2.32, -76.40, "Colombia", ("Puracé",)),
    ("Cotopaxi", -0.68, -78.44, "Ecuador", ()),
    ("Tungurahua", -1.47, -78.44, "Ecuador", ()),
    ("Sangay", -2.00, -78.34, "Ecuador", ()),
    ("Reventador", -0.08, -77.66, "Ecuador", ()),
    ("Ubinas", -16.36, -70.90, "Peru", ()),
    ("Sabancaya", -15.79, -71.86, "Peru", ()),
    ("Villarrica", -39.42, -71.93, "Chile", ()),
    ("Lascar", -23.37, -67.73, "Chile", ("Láscar",)),
    ("Copahue", -37.85, -71.17, "Chile", ()),
    ("Nevados de Chillan", -36.87, -71.38, "Chile", ()),
    ("Calbuco", -41.33, -72.61, "Chile", ()),
    # Europe and Atlantic
    ("Etna", 37.75, 14.99, "Italy", ("Mount Etna",)),
    ("Stromboli", 38.79, 15.21, "Italy", ()),
    ("Vesuvius", 40.82, 14.43, "Italy", ("Vesuvio",)),
    ("Campi Flegrei", 40.83, 14.14, "Italy", ()),
    ("Santorini", 36.40, 25.40, "Greece", ("Thera",)),
    ("Eyjafjallajokull", 63.63, -19.62, "Iceland", ("Eyjafjallajökull",)),
    ("Katla", 63.63, -19.05, "Iceland", ()),
    ("Grimsvotn", 64.42, -17.33, "Iceland", ("Grímsvötn",)),
    ("Hekla", 63.98, -19.70, "Iceland", ()),
    ("Bardarbunga", 64.64, -17.53, "Iceland", ("Bárðarbunga",)),
    ("Fagradalsfjall", 63.90, -22.27, "Iceland", ()),
    ("La Palma", 28.57, -17.83, "Spain", ("Cumbre Vieja", "Tajogaite")),
    ("Teide", 28.27, -16.64, "Spain", ()),
    ("Fogo", 14.95, -24.35, "Cape Verde", ()),
    # Caribbean
    ("Soufriere Hills", 16.72, -62.18, "Montserrat", ("Soufrière Hills",)),
    ("La Soufriere", 13.33, -61.18, "Saint Vincent", ("La Soufrière",)),
    # Africa and Indian Ocean
    ("Nyiragongo", -1.52, 29.25, "DR Congo", ()),
    ("Nyamuragira", -1.41, 29.20, "DR Congo", ("Nyamulagira",)),
    ("Ol Doinyo Lengai", -2.76, 35.91, "Tanzania", ()),
    ("Erta Ale", 13.60, 40.67, "Ethiopia", ()),
    ("Piton de la Fournaise", -21.24, 55.71, "France", ("Fournaise",)),
    # Melanesia and Pacific
    ("Manam", -4.08, 145.04, "Papua New Guinea", ()),
    ("Ulawun", -5.05, 151.33, "Papua New Guinea", ()),
    ("Rabaul", -4.27, 152.20, "Papua New Guinea", ("Tavurvur",)),
    ("Bagana", -6.14, 155.20, "Papua New Guinea", ()),
    ("Kadovar", -3.61, 144.59, "Papua New Guinea", ()),
    ("Ambae", -15.39, 167.84, "Vanuatu", ("Aoba",)),
    ("Yasur", -19.53, 169.44, "Vanuatu", ()),
    ("Ambrym", -16.25, 168.12, "Vanuatu", ()),
    ("Hunga Tonga-Hunga Ha'apai", -20.55, -175.39, "Tonga", ("Hunga Tonga",)),
    ("Home Reef", -18.99, -174.78, "Tonga", ()),
    # New Zealand and Antarctica
    ("Whakaari", -37.52, 177.18, "New Zealand", ("White Island",)),
    ("Ruapehu", -39.28, 175.57, "New Zealand", ()),
    ("Tongariro", -39.13, 175.64, "New Zealand", ()),
    ("Taupo", -38.82, 176.00, "New Zealand", ()),
    ("Erebus", -77.53, 167.17, "Antarctica", ()),
]


def slugify(name: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() else "_" for c in name)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def seed_catalogue() -> list[Volcano]:
    return [
        Volcano(
            id=f"v_{slugify(name)}",
            name=name,
            latitude=lat,
            longitude=lon,
            country=country,
            elevation_m=None,
            aliases=list(aliases),
        )
        for name, lat, lon, country, aliases in _SEED
    ]
