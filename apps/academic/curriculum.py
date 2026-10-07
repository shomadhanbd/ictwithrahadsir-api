"""The NCTB board curriculum every install starts with: SSC and HSC, their groups and exam subjects.

`seed_curriculum` writes it; a subject's slug is `<stem>-<level>-<group>`. A subject every student takes sits
under the common group (General). Staff edit the rows in the admin afterwards; re-seeding never overwrites them.
"""

#: name, slug
CLASS_LEVELS = [
    ("এসএসসি", "ssc"),
    ("এইচএসসি", "hsc"),
]

#: name, slug, common to every group
GROUPS = [
    ("বিজ্ঞান", "science", False),
    ("মানবিক", "arts", False),
    ("ব্যবসায় শিক্ষা", "commerce", False),
    ("সাধারণ", "general", True),
]


def papers(name, stem):
    """A subject examined in two papers, as the board sets it."""
    return [(f"{name} ১ম পত্র", f"{stem}-1st"), (f"{name} ২য় পত্র", f"{stem}-2nd")]


RELIGIONS = [
    ("ইসলাম ও নৈতিক শিক্ষা", "islam"),
    ("হিন্দুধর্ম ও নৈতিক শিক্ষা", "hinduism"),
    ("বৌদ্ধধর্ম ও নৈতিক শিক্ষা", "buddhism"),
    ("খ্রিষ্টধর্ম ও নৈতিক শিক্ষা", "christianity"),
]

#: class level slug -> group slug -> [(name, slug stem)], in the order they are listed
SUBJECTS = {
    "ssc": {
        "general": [
            *papers("বাংলা", "bangla"),
            *papers("ইংরেজি", "english"),
            ("গণিত", "math"),
            ("তথ্য ও যোগাযোগ প্রযুক্তি", "ict"),
            *RELIGIONS,
        ],
        "science": [
            ("পদার্থবিজ্ঞান", "physics"),
            ("রসায়ন", "chemistry"),
            ("জীববিজ্ঞান", "biology"),
            ("উচ্চতর গণিত", "higher-math"),
            ("বাংলাদেশ ও বিশ্বপরিচয়", "bgs"),
        ],
        "arts": [
            ("বাংলাদেশের ইতিহাস ও বিশ্বসভ্যতা", "history"),
            ("ভূগোল ও পরিবেশ", "geography"),
            ("পৌরনীতি ও নাগরিকতা", "civics"),
            ("অর্থনীতি", "economics"),
            ("বিজ্ঞান", "science"),
        ],
        "commerce": [
            ("হিসাববিজ্ঞান", "accounting"),
            ("ফিন্যান্স ও ব্যাংকিং", "finance-banking"),
            ("ব্যবসায় উদ্যোগ", "business-entrepreneurship"),
            ("বিজ্ঞান", "science"),
        ],
    },
    "hsc": {
        "general": [
            *papers("বাংলা", "bangla"),
            *papers("ইংরেজি", "english"),
            ("তথ্য ও যোগাযোগ প্রযুক্তি", "ict"),
        ],
        "science": [
            *papers("পদার্থবিজ্ঞান", "physics"),
            *papers("রসায়ন", "chemistry"),
            *papers("জীববিজ্ঞান", "biology"),
            *papers("উচ্চতর গণিত", "higher-math"),
        ],
        "arts": [
            *papers("অর্থনীতি", "economics"),
            *papers("পৌরনীতি ও সুশাসন", "civics"),
            *papers("ইতিহাস", "history"),
            *papers("ইসলামের ইতিহাস ও সংস্কৃতি", "islamic-history"),
            *papers("ভূগোল", "geography"),
            *papers("যুক্তিবিদ্যা", "logic"),
            *papers("সমাজবিজ্ঞান", "sociology"),
        ],
        "commerce": [
            *papers("হিসাববিজ্ঞান", "accounting"),
            *papers("ব্যবসায় সংগঠন ও ব্যবস্থাপনা", "business-management"),
            *papers("ফিন্যান্স, ব্যাংকিং ও বিমা", "finance-banking-insurance"),
            *papers("উৎপাদন ব্যবস্থাপনা ও বিপণন", "production-marketing"),
        ],
    },
}
