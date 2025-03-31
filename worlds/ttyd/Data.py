from enum import Enum


class Rels(Enum):
    aaa = "aaa"
    aji = "aji"
    bom = "bom"
    dmo = "dmo"
    dol = "dol"
    dou = "dou"
    eki = "eki"
    end = "end"
    gon = "gon"
    gor = "gor"
    gra = "gra"
    hei = "hei"
    hom = "hom"
    jin = "jin"
    jon = "jon"
    kpa = "kpa"
    las = "las"
    moo = "moo"
    mri = "mri"
    muj = "muj"
    nok = "nok"
    pik = "pik"
    rsh = "rsh"
    sys = "sys"
    tik = "tik"
    tou = "tou"
    tou2 = "tou2"
    usu = "usu"
    win = "win"
    yuu = "yuu"

class GSWType(Enum):
    GSW = 0
    GSWF = 1

starting_partners = [
    "Goombella",
    "Koops",
    "Bobbery",
    "Yoshi",
    "Flurrie",
    "Vivian",
    "Ms. Mowz"
]

shop_items = [
    78780003,
    78780019,
    78780023,
    78780030,
    78780041,
    78780053,
    78780072,
    78780073,
    78780080,
    78780096,
    78780098,
    78780102,
    78780110,
    78780111,
    78780112,
    78780118,
    78780125,
    78780131,
    78780172,
    78780173,
    78780174,
    78780175,
    78780176,
    78780177,
    78780246,
    78780247,
    78780248,
    78780249,
    78780250,
    78780251,
    78780268,
    78780271,
    78780273,
    78780274,
    78780283,
    78780284,
    78780317,
    78780316,
    78780315,
    78780313,
    78780312,
    78780310,
    78780462,
    78780463,
    78780464,
    78780465,
    78780466,
    78780469,
    78780524,
    78780525,
    78780526,
    78780529,
    78780530,
    78780531,
    78780564,
    78780566,
    78780567,
    78780569,
    78780573,
    78780574
]

location_gsw_info = {
    78780000: (GSWType.GSWF, 1247, 1),
    78780001: (GSWType.GSWF, 5568, 1),
    78780002: (GSWType.GSW, 1700, 7),
    78780004: (GSWType.GSWF, 6099, 1),
    78780045: (GSWType.GSWF, 5569, 1),
    78780046: (GSWType.GSWF, 5573, 1),
    78780047: (GSWType.GSWF, 5570, 1),
    78780048: (GSWType.GSWF, 5571, 1),
    78780049: (GSWType.GSWF, 5572, 1),
    78780055: (GSWType.GSWF, 1195, 1),
    78780060: (GSWType.GSW, 1700, 17),
    78780061: (GSWType.GSWF, 1248, 1),
    78780062: (GSWType.GSWF, 5525, 1),
    78780064: (GSWType.GSWF, 5575, 1),
    78780065: (GSWType.GSWF, 5574, 1),
    78780066: (GSWType.GSWF, 5576, 1),
    78780067: (GSWType.GSWF, 5577, 1),
    78780068: (GSWType.GSWF, 5578, 1),
    78780069: (GSWType.GSW, 1709, 3),
    78780070: (GSWType.GSW, 1709, 10),
    78780082: (GSWType.GSWF, 6100, 1),
    78780089: (GSWType.GSWF, 5528, 1),
    78780090: (GSWType.GSWF, 5527, 1),
    78780091: (GSWType.GSWF, 5580, 1),
    78780092: (GSWType.GSWF, 5581, 1),
    78780093: (GSWType.GSWF, 5582, 1),
    78780094: (GSWType.GSWF, 5579, 1),
    78780103: (GSWType.GSWF, 5584, 1),
    78780104: (GSWType.GSWF, 5583, 1),
    78780124: (GSWType.GSWF, 5530, 1),
    78780126: (GSWType.GSWF, 1354, 1),
    78780127: (GSWType.GSWF, 5586, 1),
    78780128: (GSWType.GSWF, 5587, 1),
    78780129: (GSWType.GSWF, 5588, 1),
    78780130: (GSWType.GSWF, 5585, 1),
    78780132: (GSWType.GSWF, 5589, 1),
    78780133: (GSWType.GSWF, 5531, 1),
    78780134: (GSWType.GSWF, 1356, 1),
    78780135: (GSWType.GSWF, 5590, 1),
    78780136: (GSWType.GSWF, 1337, 1),
    78780137: (GSWType.GSWF, 1357, 1),
    78780138: (GSWType.GSWF, 1358, 1),
    78780139: (GSWType.GSWF, 5591, 1),
    78780140: (GSWType.GSWF, 5532, 1),
    78780141: (GSWType.GSWF, 5592, 1),
    78780142: (GSWType.GSWF, 5593, 1),
    78780143: (GSWType.GSWF, 1359, 1),
    78780144: (GSWType.GSWF, 5533, 1),
    78780145: (GSWType.GSWF, 5595, 1),
    78780146: (GSWType.GSWF, 5594, 1),
    78780147: (GSWType.GSWF, 1362, 1),
    78780148: (GSWType.GSWF, 1363, 1),
    78780149: (GSWType.GSWF, 5534, 1),
    78780150: (GSWType.GSWF, 1364, 1),
    78780151: (GSWType.GSWF, 1365, 1),
    78780152: (GSWType.GSWF, 1366, 1),
    78780153: (GSWType.GSWF, 6055, 1),
    78780154: (GSWType.GSWF, 5597, 1),
    78780155: (GSWType.GSWF, 1367, 1),
    78780156: (GSWType.GSWF, 5535, 1),
    78780157: (GSWType.GSWF, 5536, 1),
    78780158: (GSWType.GSWF, 5537, 1),
    78780159: (GSWType.GSWF, 1368, 1),
    78780160: (GSWType.GSWF, 1802, 1),
    78780161: (GSWType.GSWF, 1785, 1),
    78780162: (GSWType.GSWF, 1784, 1),
    78780163: (GSWType.GSWF, 1786, 1),
    78780164: (GSWType.GSWF, 5600, 1),
    78780165: (GSWType.GSWF, 1787, 1),
    78780166: (GSWType.GSWF, 1791, 1),
    78780167: (GSWType.GSWF, 1790, 1),
    78780169: (GSWType.GSWF, 1775, 1),
    78780170: (GSWType.GSWF, 1796, 1),
    78780171: (GSWType.GSWF, 1774, 1),
    78780178: (GSWType.GSWF, 5601, 1),
    78780179: (GSWType.GSWF, 1628, 1),
    78780180: (GSWType.GSWF, 5602, 1),
    78780181: (GSWType.GSWF, 6101, 1),
    78780182: (GSWType.GSWF, 1780, 1),
    78780183: (GSWType.GSWF, 1778, 1),
    78780184: (GSWType.GSWF, 5598, 1),
    78780185: (GSWType.GSWF, 6077, 1),
    78780186: (GSWType.GSWF, 1800, 1),
    78780187: (GSWType.GSWF, 5599, 1),
    78780188: (GSWType.GSWF, 1799, 1),
    78780189: (GSWType.GSWF, 1797, 1),
    78780190: (GSWType.GSWF, 1798, 1),
    78780191: (GSWType.GSWF, 6102, 1),
    78780192: (GSWType.GSWF, 1501, 1),
    78780193: (GSWType.GSWF, 1502, 1),
    78780194: (GSWType.GSWF, 6002, 1),
    78780195: (GSWType.GSWF, 5603, 1),
    78780196: (GSWType.GSWF, 6006, 1),
    78780197: (GSWType.GSWF, 5538, 1),
    78780198: (GSWType.GSWF, 5604, 1),
    78780199: (GSWType.GSWF, 5605, 1),
    78780200: (GSWType.GSWF, 6009, 1),
    78780201: (GSWType.GSWF, 1503, 1),
    78780202: (GSWType.GSWF, 5539, 1),
    78780203: (GSWType.GSWF, 5606, 1),
    78780204: (GSWType.GSWF, 6011, 1),
    78780205: (GSWType.GSWF, 1504, 1),
    78780206: (GSWType.GSWF, 1494, 1),
    78780207: (GSWType.GSWF, 1505, 1),
    78780208: (GSWType.GSWF, 5607, 1),
    78780209: (GSWType.GSW, 1711, 8),
    78780210: (GSWType.GSWF, 1507, 1),
    78780211: (GSWType.GSWF, 1509, 1),
    78780212: (GSWType.GSWF, 1508, 1),
    78780213: (GSWType.GSWF, 5540, 1),
    78780214: (GSWType.GSWF, 1510, 1),
    78780215: (GSWType.GSWF, 2675, 1),
    78780216: (GSWType.GSWF, 2676, 1),
    78780217: (GSWType.GSWF, 2685, 1),
    78780218: (GSWType.GSWF, 2686, 1),
    78780219: (GSWType.GSWF, 2687, 1),
    78780220: (GSWType.GSWF, 2683, 1),
    78780221: (GSWType.GSWF, 2677, 1),
    78780222: (GSWType.GSWF, 5541, 1),
    78780223: (GSWType.GSWF, 5608, 1),
    78780224: (GSWType.GSWF, 5609, 1),
    78780225: (GSWType.GSWF, 5610, 1),
    78780226: (GSWType.GSWF, 2679, 1),
    78780227: (GSWType.GSWF, 6078, 1),
    78780228: (GSWType.GSWF, 5611, 1),
    78780229: (GSWType.GSWF, 2684, 1),
    78780230: (GSWType.GSWF, 2825, 1),
    78780231: (GSWType.GSWF, 2828, 1),
    78780232: (GSWType.GSW, 1713, 11),
    78780233: (GSWType.GSWF, 6103, 1),
    78780234: (GSWType.GSW, 1713, 5),
    78780235: (GSWType.GSWF, 5612, 1),
    78780236: (GSWType.GSWF, 5613, 1),
    78780237: (GSWType.GSWF, 2838, 1),
    78780238: (GSWType.GSWF, 2840, 1),
    78780239: (GSWType.GSWF, 2839, 1),
    78780240: (GSWType.GSWF, 2837, 1),
    78780241: (GSWType.GSWF, 5542, 1),
    78780242: (GSWType.GSWF, 2844, 1),
    78780243: (GSWType.GSWF, 6104, 1),
    78780244: (GSWType.GSWF, 2845, 1),
    78780245: (GSWType.GSWF, 5614, 1),
    78780252: (GSWType.GSWF, 2852, 1),
    78780253: (GSWType.GSWF, 2853, 1),
    78780254: (GSWType.GSWF, 5543, 1),
    78780255: (GSWType.GSWF, 6025, 1),
    78780256: (GSWType.GSWF, 2860, 1),
    78780257: (GSWType.GSWF, 5615, 1),
    78780258: (GSWType.GSWF, 2862, 1),
    78780259: (GSWType.GSWF, 5616, 1),
    78780260: (GSWType.GSWF, 2869, 1),
    78780261: (GSWType.GSWF, 5544, 1),
    78780262: (GSWType.GSWF, 2885, 1),
    78780263: (GSWType.GSWF, 5617, 1),
    78780264: (GSWType.GSWF, 2873, 1),
    78780265: (GSWType.GSWF, 5545, 1),
    78780266: (GSWType.GSWF, 2875, 1),
    78780267: (GSWType.GSWF, 2507, 1),
    78780269: (GSWType.GSWF, 6105, 1),
    78780270: (GSWType.GSWF, 2533, 1),
    78780272: (GSWType.GSWF, 2519, 1),
    78780275: (GSWType.GSWF, 5546, 1),
    78780276: (GSWType.GSWF, 5618, 1),
    78780277: (GSWType.GSWF, 5619, 1),
    78780278: (GSWType.GSWF, 5620, 1),
    78780279: (GSWType.GSWF, 5622, 1),
    78780280: (GSWType.GSWF, 5621, 1),
    78780281: (GSWType.GSWF, 6027, 1),
    78780282: (GSWType.GSWF, 6026, 1),
    78780285: (GSWType.GSWF, 5623, 1),
    78780286: (GSWType.GSWF, 6028, 1),
    78780287: (GSWType.GSW, 1703, 20),
    78780288: (GSWType.GSWF, 2520, 1),
    78780289: (GSWType.GSWF, 5624, 1),
    78780290: (GSWType.GSWF, 5625, 1),
    78780291: (GSWType.GSWF, 2523, 1),
    78780292: (GSWType.GSWF, 2521, 1),
    78780293: (GSWType.GSWF, 5547, 1),
    78780294: (GSWType.GSWF, 5626, 1),
    78780295: (GSWType.GSWF, 2378, 1),
    78780296: (GSWType.GSWF, 2524, 1),
    78780297: (GSWType.GSWF, 6036, 1),
    78780298: (GSWType.GSWF, 6079, 1),
    78780299: (GSWType.GSWF, 5627, 1),
    78780300: (GSWType.GSWF, 1933, 1),
    78780301: (GSWType.GSWF, 6106, 1),
    78780302: (GSWType.GSWF, 5628, 1),
    78780303: (GSWType.GSWF, 5629, 1),
    78780304: (GSWType.GSWF, 6040, 1),
    78780305: (GSWType.GSWF, 6080, 1),
    78780306: (GSWType.GSWF, 1936, 1),
    78780307: (GSWType.GSWF, 1934, 1),
    78780308: (GSWType.GSWF, 1939, 1),
    78780309: (GSWType.GSWF, 1937, 1),
    78780311: (GSWType.GSWF, 1935, 1),
    78780314: (GSWType.GSWF, 5630, 1),
    78780318: (GSWType.GSWF, 6043, 1),
    78780319: (GSWType.GSWF, 2089, 1),
    78780320: (GSWType.GSWF, 2091, 1),
    78780321: (GSWType.GSWF, 2088, 1),
    78780322: (GSWType.GSWF, 2082, 1),
    78780323: (GSWType.GSWF, 2087, 1),
    78780324: (GSWType.GSWF, 6041, 1),
    78780325: (GSWType.GSWF, 5631, 1),
    78780326: (GSWType.GSWF, 5632, 1),
    78780327: (GSWType.GSWF, 2083, 1),
    78780328: (GSWType.GSWF, 2084, 1),
    78780329: (GSWType.GSWF, 2086, 1),
    78780330: (GSWType.GSWF, 2085, 1),
    78780331: (GSWType.GSWF, 5548, 1),
    78780332: (GSWType.GSWF, 2090, 1),
    78780333: (GSWType.GSWF, 5633, 1),
    78780434: (GSWType.GSWF, 2242, 1),
    78780435: (GSWType.GSWF, 6046, 1),
    78780436: (GSWType.GSWF, 6107, 1),
    78780437: (GSWType.GSW, 1715, 8),
    78780438: (GSWType.GSWF, 2235, 1),
    78780439: (GSWType.GSWF, 2237, 1),
    78780440: (GSWType.GSWF, 5549, 1),
    78780441: (GSWType.GSWF, 5635, 1),
    78780442: (GSWType.GSWF, 2238, 1),
    78780443: (GSWType.GSWF, 5636, 1),
    78780444: (GSWType.GSW, 1716, 1),
    78780445: (GSWType.GSWF, 2240, 1),
    78780446: (GSWType.GSWF, 2239, 1),
    78780447: (GSWType.GSWF, 5637, 1),
    78780448: (GSWType.GSWF, 2230, 1),
    78780449: (GSWType.GSWF, 6049, 1),
    78780450: (GSWType.GSWF, 5550, 1),
    78780451: (GSWType.GSWF, 2241, 1),
    78780452: (GSWType.GSWF, 5551, 1),
    78780453: (GSWType.GSWF, 5638, 1),
    78780454: (GSWType.GSWF, 6082, 1),
    78780455: (GSWType.GSWF, 6083, 1),
    78780456: (GSWType.GSWF, 6084, 1),
    78780457: (GSWType.GSWF, 6085, 1),
    78780458: (GSWType.GSWF, 6086, 1),
    78780459: (GSWType.GSWF, 6087, 1),
    78780460: (GSWType.GSWF, 6088, 1),
    78780461: (GSWType.GSW, 1719, 4),
    78780467: (GSWType.GSWF, 5639, 1),
    78780468: (GSWType.GSWF, 5640, 1),
    78780470: (GSWType.GSWF, 3154, 1),
    78780471: (GSWType.GSWF, 3150, 1),
    78780472: (GSWType.GSWF, 3146, 1),
    78780473: (GSWType.GSWF, 3152, 1),
    78780474: (GSWType.GSWF, 5641, 1),
    78780475: (GSWType.GSWF, 3134, 1),
    78780476: (GSWType.GSWF, 3133, 1),
    78780477: (GSWType.GSWF, 3156, 1),
    78780478: (GSWType.GSWF, 3153, 1),
    78780479: (GSWType.GSWF, 3155, 1),
    78780480: (GSWType.GSWF, 5552, 1),
    78780481: (GSWType.GSWF, 5642, 1),
    78780482: (GSWType.GSWF, 3147, 1),
    78780483: (GSWType.GSWF, 6090, 1),
    78780484: (GSWType.GSWF, 6091, 1),
    78780485: (GSWType.GSWF, 3148, 1),
    78780486: (GSWType.GSWF, 3158, 1),
    78780487: (GSWType.GSWF, 5553, 1),
    78780488: (GSWType.GSWF, 6081, 1),
    78780489: (GSWType.GSWF, 6108, 1),
    78780490: (GSWType.GSWF, 3157, 1),
    78780491: (GSWType.GSWF, 5643, 1),
    78780492: (GSWType.GSWF, 3143, 1),
    78780493: (GSWType.GSWF, 2990, 1),
    78780494: (GSWType.GSWF, 2975, 1),
    78780495: (GSWType.GSWF, 5554, 1),
    78780496: (GSWType.GSWF, 5644, 1),
    78780497: (GSWType.GSWF, 5645, 1),
    78780498: (GSWType.GSWF, 2977, 1),
    78780499: (GSWType.GSWF, 5555, 1),
    78780500: (GSWType.GSWF, 5646, 1),
    78780501: (GSWType.GSWF, 2993, 1),
    78780502: (GSWType.GSWF, 2986, 1),
    78780503: (GSWType.GSWF, 5556, 1),
    78780504: (GSWType.GSWF, 5647, 1),
    78780505: (GSWType.GSWF, 2987, 1),
    78780506: (GSWType.GSWF, 6052, 1),
    78780507: (GSWType.GSWF, 2985, 1),
    78780508: (GSWType.GSWF, 2994, 1),
    78780509: (GSWType.GSWF, 5557, 1),
    78780510: (GSWType.GSWF, 5558, 1),
    78780511: (GSWType.GSW, 1717, 10),
    78780512: (GSWType.GSW, 1706, 13),
    78780513: (GSWType.GSWF, 5648, 1),
    78780514: (GSWType.GSW, 1706, 25),
    78780515: (GSWType.GSWF, 6092, 1),
    78780516: (GSWType.GSW, 1706, 20),
    78780517: (GSWType.GSW, 1706, 29),
    78780518: (GSWType.GSWF, 3462, 1),
    78780519: (GSWType.GSW, 1706, 7),
    78780520: (GSWType.GSW, 1706, 29),
    78780521: (GSWType.GSW, 1706, 29),
    78780522: (GSWType.GSWF, 5559, 1),
    78780523: (GSWType.GSWF, 5649, 1),
    78780527: (GSWType.GSWF, 5650, 1),
    78780528: (GSWType.GSWF, 5651, 1),
    78780532: (GSWType.GSW, 1706, 21),
    78780533: (GSWType.GSWF, 5560, 1),
    78780534: (GSWType.GSWF, 5652, 1),
    78780535: (GSWType.GSW, 1706, 19),
    78780536: (GSWType.GSW, 1720, 2),
    78780537: (GSWType.GSWF, 3745, 1),
    78780538: (GSWType.GSWF, 5653, 1),
    78780539: (GSWType.GSWF, 6059, 1),
    78780540: (GSWType.GSWF, 3746, 1),
    78780541: (GSWType.GSWF, 5561, 1),
    78780542: (GSWType.GSWF, 3754, 1),
    78780543: (GSWType.GSWF, 3744, 1),
    78780544: (GSWType.GSWF, 3747, 1),
    78780545: (GSWType.GSWF, 6065, 1),
    78780546: (GSWType.GSWF, 6064, 1),
    78780547: (GSWType.GSWF, 5562, 1),
    78780548: (GSWType.GSWF, 3874, 1),
    78780549: (GSWType.GSWF, 3276, 1),
    78780550: (GSWType.GSWF, 5654, 1),
    78780551: (GSWType.GSWF, 5656, 1),
    78780552: (GSWType.GSWF, 5655, 1),
    78780553: (GSWType.GSWF, 5563, 1),
    78780554: (GSWType.GSW, 1706, 42),
    78780555: (GSWType.GSWF, 3277, 1),
    78780556: (GSWType.GSWF, 5564, 1),
    78780557: (GSWType.GSWF, 6109, 1),
    78780558: (GSWType.GSWF, 3279, 1),
    78780559: (GSWType.GSWF, 6110, 1),
    78780560: (GSWType.GSWF, 5657, 1),
    78780561: (GSWType.GSWF, 3891, 1),
    78780562: (GSWType.GSWF, 5658, 1),
    78780563: (GSWType.GSWF, 5659, 1),
    78780565: (GSWType.GSWF, 3892, 1),
    78780568: (GSWType.GSWF, 5565, 1),
    78780570: (GSWType.GSWF, 6111, 1),
    78780571: (GSWType.GSWF, 5661, 1),
    78780572: (GSWType.GSWF, 5660, 1),
    78780575: (GSWType.GSWF, 5566, 1),
    78780576: (GSWType.GSWF, 5662, 1),
    78780577: (GSWType.GSWF, 3887, 1),
    78780578: (GSWType.GSWF, 5663, 1),
    78780579: (GSWType.GSWF, 4035, 1),
    78780580: (GSWType.GSWF, 4037, 1),
    78780581: (GSWType.GSWF, 5664, 1),
    78780582: (GSWType.GSWF, 4038, 1),
    78780583: (GSWType.GSWF, 4039, 1),
    78780584: (GSWType.GSWF, 4176, 1),
    78780585: (GSWType.GSWF, 4211, 1),
    78780586: (GSWType.GSWF, 6093, 1),
    78780587: (GSWType.GSWF, 6094, 1),
    78780588: (GSWType.GSWF, 6095, 1),
    78780589: (GSWType.GSWF, 6096, 1),
    78780590: (GSWType.GSWF, 6097, 1),
    78780591: (GSWType.GSWF, 6098, 1),
    78780592: (GSWType.GSWF, 4198, 1),
    78780593: (GSWType.GSWF, 4216, 1),
    78780594: (GSWType.GSWF, 5665, 1),
    78780595: (GSWType.GSWF, 6069, 1),
    78780596: (GSWType.GSWF, 4182, 1),
    78780597: (GSWType.GSWF, 4212, 1),
    78780598: (GSWType.GSWF, 4194, 1),
    78780599: (GSWType.GSWF, 5666, 1),
    78780600: (GSWType.GSWF, 4180, 1),
    78780601: (GSWType.GSWF, 4183, 1),
    78780602: (GSWType.GSWF, 4181, 1),
    78780603: (GSWType.GSWF, 4215, 1),
    78780604: (GSWType.GSW, 1707, 16),
    78780605: (GSWType.GSWF, 4383, 1),
    78780606: (GSWType.GSWF, 4371, 1),
    78780607: (GSWType.GSWF, 4375, 1),
    78780608: (GSWType.GSWF, 4384, 1),
    78780609: (GSWType.GSWF, 6071, 1),
    78780610: (GSWType.GSWF, 4372, 1),
    78780611: (GSWType.GSWF, 4373, 1),
    78780612: (GSWType.GSWF, 4374, 1),
    78780613: (GSWType.GSWF, 4376, 1),
    78780614: (GSWType.GSWF, 4362, 1),
    78780615: (GSWType.GSWF, 4363, 1),
    78780616: (GSWType.GSWF, 4364, 1),
    78780617: (GSWType.GSWF, 4365, 1),
    78780618: (GSWType.GSWF, 4366, 1),
    78780619: (GSWType.GSWF, 4367, 1),
    78780620: (GSWType.GSWF, 4368, 1),
    78780621: (GSWType.GSWF, 4369, 1),
    78780622: (GSWType.GSWF, 4387, 1),
    78780623: (GSWType.GSWF, 4378, 1),
    78780624: (GSWType.GSWF, 4388, 1),
    78780625: (GSWType.GSWF, 4379, 1),
    78780626: (GSWType.GSWF, 6073, 1),
    78780627: (GSWType.GSWF, 4377, 1),
    78780628: (GSWType.GSWF, 4390, 1),
    78780629: (GSWType.GSWF, 4370, 1),
    78780630: (GSWType.GSWF, 4391, 1),
    78780631: (GSWType.GSWF, 4379, 1),
    78780632: (GSWType.GSWF, 4392, 1),
    78780633: (GSWType.GSWF, 4386, 1),
    78780634: (GSWType.GSWF, 4361, 1),
    78780635: (GSWType.GSWF, 4385, 1),
    78780636: (GSWType.GSWF, 4394, 1),
    78780637: (GSWType.GSWF, 4393, 1),
    78780638: (GSWType.GSWF, 5075, 1),
    78780639: (GSWType.GSWF, 5076, 1),
    78780640: (GSWType.GSWF, 5077, 1),
    78780641: (GSWType.GSWF, 5078, 1),
    78780642: (GSWType.GSWF, 5079, 1),
    78780643: (GSWType.GSWF, 5080, 1),
    78780644: (GSWType.GSWF, 5081, 1),
    78780645: (GSWType.GSWF, 5082, 1),
    78780646: (GSWType.GSWF, 5083, 1),
    78780647: (GSWType.GSWF, 5084, 1),
    78780702: (GSWType.GSWF, 4214, 1),
    78780704: (GSWType.GSWF, 5596, 1),
    78780705: (GSWType.GSWF, 1355, 1),
    78780706: (GSWType.GSWF, 5567, 1),
    78780707: (GSWType.GSWF, 5526, 1),
    78780708: (GSWType.GSWF, 5529, 1),
    78780800: (GSWType.GSWF, 1801, 1),
    78780801: (GSWType.GSWF, 1794, 1),
    78780802: (GSWType.GSWF, 1795, 1),
    78780803: (GSWType.GSWF, 1806, 1),
    78780805: (GSWType.GSWF, 5634, 1),
    78780806: (GSWType.GSWF, 6089, 1),
    78780807: (GSWType.GSWF, 4036, 1)
}

shop_data = {
    "gor_01": [78780030, 78780023, 78780053, 78780003, 78780041, 78780019],
    "gor_03": [78780096, 78780102, 78780073, 78780080, 78780072, 78780098],
    "tik_00": [78780125, 78780112, 78780131, 78780118, 78780110, 78780111],
    "nok_00": [78780173, 78780177, 78780172, 78780175, 78780174, 78780176],
    "mri_07": [78780247, 78780248, 78780251, 78780249, 78780246, 78780250],
    "tou_01": [78780268, 78780284, 78780273, 78780274, 78780271, 78780283],
    "usu_01": [78780317, 78780313, 78780315, 78780312, 78780316, 78780310],
    "muj_01": [78780465, 78780462, 78780466, 78780463, 78780464, 78780469],
    "rsh_03": [78780531, 78780526, 78780524, 78780530, 78780525, 78780529],
    "bom_02": [78780569, 78780564, 78780567, 78780573, 78780566, 78780574],
}

tubu_dt = {
    0x37491E: 0x0003,
    0x37492A: 0x000C,
    0x374936: 0x000C,
    0x374942: 0x000C,
    0x37494E: 0x0001,
    0x37495A: 0x0003,
    0x374966: 0x0003,
    0x374972: 0x0003,
    0x37497E: 0x0003,
    0x37498A: 0x0002,
    0x374996: 0x0002,
    0x3749A2: 0x0002,
    0x3749AE: 0x0002,
    0x3749BA: 0x0001,
    0x3749C6: 0x0003,
    0x3749D2: 0x0003,
    0x3749DE: 0x0010,
    0x3749EA: 0x0010,
    0x3749F6: 0x0010,
    0x374A02: 0x0001,
    0x374A0E: 0x0001,
    0x374A1A: 0x0001,
    0x374A26: 0x0001,
    0x374A32: 0x0001,
    0x374A3E: 0x0001,
    0x374A4A: 0x0001,
    0x374A56: 0x0001,
    0x374A62: 0x0001,
    0x374A6E: 0x0001,
    0x374A7A: 0x0001,
    0x374A86: 0x0001,
    0x374A92: 0x0001,
    0x374A9E: 0x0002,
    0x374AAA: 0x0007,
    0x374AB6: 0x0007,
    0x374AC2: 0x0007,
    0x374ACE: 0x0007,
    0x374ADA: 0x0007,
    0x374AE6: 0x0007,
    0x374AF2: 0x0007,
    0x374AFE: 0x0007,
    0x374B0A: 0x0007,
    0x374B16: 0x0006,
    0x374B22: 0x0006,
    0x374B2E: 0x0006,
    0x374B3A: 0x0006,
    0x374B46: 0x0006,
    0x374B52: 0x0006,
    0x374B5E: 0x0010,
    0x374B6A: 0x0010,
    0x374B76: 0x0010,
    0x374B82: 0x0010,
    0x374B8E: 0x0010,
    0x374B9A: 0x0010,
    0x374BA6: 0x0010,
    0x374BB2: 0x0010,
    0x374BBE: 0x0010,
    0x374BCA: 0x0010,
    0x374BD6: 0x0002,
    0x374BE2: 0x0002,
    0x374BEE: 0x0002,
    0x374BFA: 0x0001,
    0x374C06: 0x0001,
    0x374C12: 0x0001,
    0x374C1E: 0x0001,
    0x374C2A: 0x0001,
    0x374C36: 0x0001,
    0x374C42: 0x0001,
    0x374C4E: 0x0001,
    0x374C5A: 0x0038,
    0x374C66: 0x0038,
    0x374C72: 0x0038,
    0x374C7E: 0x0038,
    0x374C8A: 0x0038,
    0x374C96: 0x0040,
    0x374CA2: 0x0040,
    0x374CAE: 0x0040,
    0x374CBA: 0x0002,
    0x374CC6: 0x0006,
    0x374CD2: 0x0006,
    0x374CDE: 0x0006,
    0x374CEA: 0x0006,
    0x374CF6: 0x0006,
    0x374D02: 0x0006,
    0x374D0E: 0x0006,
    0x374D1A: 0x0006,
    0x374D26: 0x0009,
    0x374D32: 0x0009,
    0x374D3E: 0x0009,
    0x374D4A: 0x0009,
    0x374D56: 0x0002,
    0x374D62: 0x0002,
    0x374D6E: 0x0002
}