"""Five test courses covering each delivery, audience, lesson type and package kind; see `seed_test_courses`.

Days are relative to the run: `release` and `live_in` are days from now (negative is past).
"""

STUDENT_NAME = "Sayed"  # the enrolled student, matched by the start of their name

COURSES = [
    {
        "slug": "demo-hsc-physics-live-2027",
        "title": "HSC Physics Live Batch 2027",
        "subtitle": "সপ্তাহে ৩টি লাইভ ক্লাস, ক্লাস নোট আর অধ্যায়ভিত্তিক পরীক্ষা",
        "colors": ("#1e3a8a", "#7c3aed"),
        "delivery": "live",
        "is_online": True,
        "difficulty": "intermediate",
        "level": "hsc",
        "group": "science",
        "starts_in": -20,
        "ends_in": 150,
        "duration": "৬ মাস",
        "routines": ["শনি, সোম, বুধ — রাত ৮টা", "প্রতি শুক্রবার সাপ্তাহিক পরীক্ষা"],
        "package": {"title": "Physics Live — 6 months", "price": 2500, "base_price": 3000, "access_days": 180},
        "chapters": [
            (
                "ভৌত জগৎ ও পরিমাপ",
                [
                    ("live", "লাইভ ক্লাস ১: পরিমাপের একক", {"live_in": -6}),
                    ("note", "ক্লাস নোট: মাত্রা ও একক", {"free": True}),
                    ("pdf", "লেকচার শিট ১", {}),
                    ("exam", "অধ্যায় ১ পরীক্ষা", {}),
                ],
            ),
            (
                "ভেক্টর",
                [
                    ("live", "লাইভ ক্লাস ২: ভেক্টরের যোগ", {"live_in": 2}),
                    ("video", "রেকর্ডিং: ভেক্টরের গুণন", {}),
                    ("note", "সূত্রের তালিকা", {}),
                ],
            ),
        ],
        # Enrolled, two lessons done, access ending in two days (so renewal is open).
        "enroll": {"ends_in_days": 2, "done": 2},
    },
    {
        "slug": "demo-ssc-ict-recorded",
        "title": "SSC ICT Complete Course",
        "subtitle": "পুরো সিলেবাস রেকর্ডেড ভিডিওতে, যখন খুশি দেখুন",
        "colors": ("#065f46", "#0ea5e9"),
        "delivery": "recorded",
        "is_online": True,
        "difficulty": "beginner",
        "level": "ssc",
        "group": "general",
        "duration": "আজীবন",
        "package": {"title": "SSC ICT — lifetime", "price": 1500, "base_price": 1500},
        "chapters": [
            (
                "তথ্য ও যোগাযোগ প্রযুক্তি পরিচিতি",
                [
                    ("video", "ICT কী এবং কেন", {"free": True}),
                    ("video", "বিশ্বগ্রাম ধারণা", {}),
                    ("note", "অধ্যায়ের সারসংক্ষেপ", {}),
                ],
            ),
            (
                "কম্পিউটার ও কম্পিউটার ব্যবহারকারীর নিরাপত্তা",
                [
                    ("video", "ভাইরাস ও এন্টিভাইরাস", {}),
                    ("link", "অনুশীলনের ওয়েবসাইট", {}),
                    ("pdf", "প্র্যাকটিস শিট", {}),
                ],
            ),
        ],
        # Enrolled for life and finished: every lesson done.
        "enroll": {"ends_in_days": None, "done": "all"},
    },
    {
        "slug": "demo-hsc-chemistry-hybrid",
        "title": "HSC Chemistry Hybrid Program",
        "subtitle": "সেন্টারে সরাসরি ক্লাস আর অনলাইনে রেকর্ডিং — দুটোই",
        "colors": ("#9a3412", "#f59e0b"),
        "delivery": "hybrid",
        "is_online": False,
        "difficulty": "advanced",
        "level": "hsc",
        "group": "science",
        "starts_in": 10,
        "ends_in": 200,
        "enrollment_deadline_in": 30,
        "duration": "৩১ মার্চ ২০২৭ পর্যন্ত",
        "routines": ["রবি ও বৃহস্পতি — বিকাল ৪টা (সেন্টারে)"],
        "package": {
            "title": "Chemistry Hybrid — till 31 Mar 2027",
            "price": 4000,
            "base_price": 5000,
            "access_ends_on": "2027-03-31",
            "discount_days": 7,
        },
        "chapters": [
            (
                "ল্যাবরেটরির নিরাপদ ব্যবহার",
                [
                    ("video", "পরিচিতি ক্লাস", {"free": True}),
                    ("live", "সেন্টারের প্রথম ক্লাস", {"live_in": 10}),
                    ("pdf", "ল্যাব ম্যানুয়াল", {}),
                ],
            ),
            (
                "গুণগত রসায়ন",
                [
                    ("video", "পরমাণুর গঠন", {"release": 14}),
                    ("note", "কোয়ান্টাম সংখ্যা", {"release": 14}),
                    ("exam", "অধ্যায় ২ পরীক্ষা", {"release": 21}),
                ],
            ),
        ],
    },
    {
        "slug": "demo-hsc-accounting-crash",
        "title": "HSC Accounting Crash Course",
        "subtitle": "বোর্ড পরীক্ষার আগে ৯০ দিনে পুরো হিসাববিজ্ঞান",
        "colors": ("#831843", "#f43f5e"),
        "delivery": "recorded",
        "is_online": True,
        "difficulty": "intermediate",
        "level": "hsc",
        "group": "commerce",
        "starts_in": -100,
        "duration": "৯০ দিন",
        "package": {"title": "Accounting — 90 days", "price": 1200, "base_price": 1800, "access_days": 90},
        "chapters": [
            (
                "হিসাববিজ্ঞান পরিচিতি",
                [
                    ("video", "লেনদেন ও হিসাব", {"free": True}),
                    ("video", "দুতরফা দাখিলা পদ্ধতি", {"release": -90}),
                    ("note", "গুরুত্বপূর্ণ সংজ্ঞা", {"release": -90}),
                ],
            ),
            (
                "জাবেদা ও খতিয়ান",
                [
                    ("video", "জাবেদা লেখার নিয়ম", {"release": -80}),
                    ("pdf", "অনুশীলনী সমাধান", {"release": -80}),
                ],
            ),
        ],
        # Bought 90 days' access that ran out five days ago, one lesson in.
        "enroll": {"ends_in_days": -5, "done": 1},
    },
    {
        "slug": "demo-hsc-ict-model-tests",
        "title": "HSC ICT Model Test Series",
        "subtitle": "ফ্রি মডেল টেস্ট — নিজেকে যাচাই করুন",
        "colors": ("#0f172a", "#22c55e"),
        "delivery": "live",
        "is_online": True,
        "difficulty": "beginner",
        "level": "hsc",
        "group": "general",
        "duration": "৪ সপ্তাহ",
        "package": {"title": "Model tests — free", "price": 0, "base_price": 0},
        "chapters": [
            (
                "মডেল টেস্ট",
                [
                    ("note", "পরীক্ষার নিয়মাবলি", {"free": True}),
                    ("exam", "মডেল টেস্ট ১", {"publish": 5}),
                    ("exam", "মডেল টেস্ট ২", {"publish": 5}),
                    ("live", "সমাধান ক্লাস", {"live_in": 7}),
                ],
            ),
        ],
    },
]

OUTCOMES = [
    "প্রতিটি অধ্যায়ের মূল ধারণা সহজ ভাষায়",
    "বোর্ড প্রশ্নের ধরন ও উত্তর লেখার কৌশল",
    "সাপ্তাহিক পরীক্ষায় নিজের অবস্থান যাচাই",
    "ক্লাস শেষে নোট ও লেকচার শিট",
]
HIGHLIGHTS = ["অভিজ্ঞ শিক্ষক", "লেকচার শিট", "পরীক্ষা ও র‍্যাঙ্কিং", "প্রশ্নোত্তর সেশন"]
FAQS = [
    ("ক্লাস মিস করলে কী হবে?", "প্রতিটি ক্লাসের রেকর্ডিং ও নোট কোর্সে থাকবে।"),
    ("কোন ডিভাইসে দেখা যাবে?", "মোবাইল, ট্যাব বা কম্পিউটার — যেকোনোটিতে।"),
]
VIDEO = "https://www.youtube.com/watch?v=K3R-NRESyzU"
