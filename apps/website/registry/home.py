"""The home page, top to bottom. `syllabus` and `app_download` are shared with the About and notice pages."""

from apps.website.registry.fields import (
    SOCIAL_PLATFORMS,
    STAT_METRICS,
    SectionSpec,
    choice,
    heading,
    icon,
    image,
    items,
    link,
    subtitle,
    text,
    textarea,
)

SECTIONS = (
    SectionSpec(
        "home.hero",
        "home",
        "Hero",
        can_hide=False,
        description="The first screen. Banners, when there are any, replace the photo beside the heading.",
        fields=(
            text("badge", "Badge", "সিলেটে সেন্টার · সারাদেশে অনলাইন"),
            text(
                "title",
                "Heading",
                "*ICT*-তে *A+* পাওয়ার স্মার্ট প্রস্তুতি — রাহাদ স্যারের সাথে",
                required=True,
                help="Put *stars* around words to colour them.",
            ),
            textarea(
                "subtitle",
                "Subtitle",
                "ক্লিয়ার কনসেপ্ট, শর্ট টেকনিক আর বোর্ড প্রশ্নের নিয়মিত অনুশীলন — এসএসসি ও এইচএসসি আইসিটির সব প্রস্তুতি এক জায়গায়।",
            ),
            items(
                "points",
                "Ticked points",
                [text("text", "Point", required=True)],
                [
                    {"text": "এসএসসি ও এইচএসসি আইসিটি"},
                    {"text": "লাইভ + রেকর্ডেড ক্লাস"},
                    {"text": "অধ্যায়ভিত্তিক পরীক্ষা ও র‍্যাঙ্কিং"},
                ],
                max_items=4,
            ),
            text("button_label", "Button", "কোর্স দেখুন", required=True),
            link("button_link", "Button link", "/course", required=True),
            image(
                "image",
                "Photo",
                "https://rahad-ict.sgp1.digitaloceanspaces.com/pages/kgK8lRrSMHyTf9BPgkDsPqL6U1SEt2fR.jpg",
                help="Shown beside the heading until a banner is added under Banners.",
            ),
        ),
    ),
    SectionSpec(
        "home.stats",
        "home",
        "Numbers",
        description="Counted from the site unless you type a number; a number of 0 is not shown.",
        fields=(
            items(
                "items",
                "Numbers",
                [
                    choice("metric", "Count", STAT_METRICS, "courses"),
                    text("label", "Label", required=True),
                    text("value", "Number to show instead", help="Leave empty to use the count; e.g. ৫০০০+"),
                ],
                [
                    {"metric": "courses", "label": "প্রিমিয়াম কোর্স", "value": ""},
                    {"metric": "students", "label": "সন্তুষ্ট শিক্ষার্থী", "value": ""},
                    {"metric": "teachers", "label": "দক্ষ শিক্ষক", "value": ""},
                ],
                max_items=4,
            ),
        ),
    ),
    SectionSpec(
        "home.classes",
        "home",
        "Class picker",
        fields=(
            heading("আপনি কোন শ্রেণিতে পড়েন?"),
            subtitle("আপনার শ্রেণি বেছে নিন — আপনার জন্য সাজানো কোর্সগুলো দেখুন।"),
            items(
                "cards",
                "Classes",
                [
                    text("class_level", "Class slug", required=True, help="e.g. hsc or ssc; filters the course list."),
                    text("title", "Title", required=True),
                    text("subtitle", "Subtitle"),
                    textarea("text", "Text"),
                ],
                [
                    {
                        "class_level": "hsc",
                        "title": "এইচএসসি",
                        "subtitle": "একাদশ ও দ্বাদশ শ্রেণি",
                        "text": "পুরো সিলেবাস, বোর্ড প্রশ্ন সমাধান আর মডেল টেস্ট।",
                    },
                    {
                        "class_level": "ssc",
                        "title": "এসএসসি",
                        "subtitle": "নবম ও দশম শ্রেণি",
                        "text": "আইসিটির ভিত্তি মজবুত করুন শুরু থেকেই।",
                    },
                ],
                max_items=4,
            ),
        ),
    ),
    SectionSpec(
        "home.courses",
        "home",
        "Courses",
        description="Featured courses, or the newest when none is featured.",
        fields=(
            text("featured_heading", "Heading (featured)", "জনপ্রিয় কোর্স", required=True),
            textarea("featured_subtitle", "Subtitle (featured)", "এই মুহূর্তে সবচেয়ে বেশি শিক্ষার্থী যেগুলোতে ভর্তি হচ্ছেন।"),
            text("newest_heading", "Heading (newest)", "নতুন কোর্স", required=True),
            textarea("newest_subtitle", "Subtitle (newest)", "সদ্য শুরু হওয়া কোর্সগুলো দেখে নিন।"),
        ),
    ),
    SectionSpec(
        "syllabus",
        "home",
        "Syllabus",
        description="The chapters also appear on the About page.",
        fields=(
            heading("এইচএসসি আইসিটি সিলেবাস — ৬ অধ্যায়"),
            subtitle("বোর্ডের সিলেবাস অনুযায়ী প্রতিটি অধ্যায় আলাদা করে — কনসেপ্ট, বোর্ড প্রশ্ন আর অনুশীলন একসাথে।"),
            items(
                "chapters",
                "Chapters",
                [icon(), text("title", "Title", required=True), textarea("topics", "Topics")],
                [
                    {
                        "icon": "globe",
                        "title": "তথ্য ও যোগাযোগ প্রযুক্তি: বিশ্ব ও বাংলাদেশ প্রেক্ষিত",
                        "topics": "ভার্চুয়াল রিয়েলিটি, বায়োমেট্রিক্স, ন্যানোটেকনোলজি, আইসিটির নৈতিকতা",
                    },
                    {
                        "icon": "network",
                        "title": "কমিউনিকেশন সিস্টেমস ও নেটওয়ার্কিং",
                        "topics": "ডেটা ট্রান্সমিশন, ব্যান্ডউইথ, নেটওয়ার্ক টপোলজি, ক্লাউড কম্পিউটিং",
                    },
                    {
                        "icon": "binary",
                        "title": "সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস",
                        "topics": "বাইনারি-অক্টাল-হেক্সাডেসিমাল, লজিক গেট, অ্যাডার, এনকোডার-ডিকোডার",
                    },
                    {
                        "icon": "code-xml",
                        "title": "ওয়েব ডিজাইন পরিচিতি ও এইচটিএমএল",
                        "topics": "ওয়েবসাইট স্ট্রাকচার, এইচটিএমএল ট্যাগ, সিএসএস, ওয়েব পাবলিশিং",
                    },
                    {
                        "icon": "braces",
                        "title": "প্রোগ্রামিং ভাষা",
                        "topics": "সি ভাষার বেসিক, কন্ট্রোল স্টেটমেন্ট, লুপ, অ্যারে, ফাংশন",
                    },
                    {
                        "icon": "database",
                        "title": "ডেটাবেজ ম্যানেজমেন্ট সিস্টেম",
                        "topics": "টেবিল ও রিলেশন, কুয়েরি, এসকিউএল, ডেটা সিকিউরিটি",
                    },
                ],
            ),
        ),
    ),
    SectionSpec(
        "home.features",
        "home",
        "What a course includes",
        fields=(
            heading("কোর্সে যা যা পাচ্ছেন"),
            subtitle("ক্লাস, পরীক্ষা আর নোট — আইসিটির প্রস্তুতির সবকিছু একই জায়গায়।"),
            items(
                "items",
                "Features",
                [icon(), text("title", "Title", required=True), textarea("text", "Text")],
                [
                    {
                        "icon": "monitor-play",
                        "title": "রেকর্ডেড ভিডিও ক্লাস",
                        "text": "প্রতিটি অধ্যায়ের ক্লাস, যতবার খুশি দেখা যায় — নিজের গতিতে।",
                    },
                    {"icon": "radio", "title": "লাইভ ক্লাস", "text": "সরাসরি ক্লাসে যুক্ত হয়ে তখনই প্রশ্ন করার সুযোগ।"},
                    {
                        "icon": "list-checks",
                        "title": "অধ্যায়ভিত্তিক এমসিকিউ পরীক্ষা",
                        "text": "পড়া শেষে পরীক্ষা, সাথে সাথেই ফলাফল আর ভুলের ব্যাখ্যা।",
                    },
                    {
                        "icon": "file-text",
                        "title": "লেকচার শিট ও শর্টনোট",
                        "text": "পিডিএফে গোছানো নোট — রিভিশনের সময় বই ঘাঁটতে হয় না।",
                    },
                    {"icon": "calendar-clock", "title": "ক্লাস রুটিন", "text": "কবে কোন ক্লাস, কোন অধ্যায় — আগেই জানা থাকে।"},
                    {
                        "icon": "message-circle-question",
                        "title": "২৪/৭ সাপোর্ট",
                        "text": "আটকে গেলে প্রশ্ন করুন, উত্তর পাবেন সাপোর্ট থ্রেডে।",
                    },
                ],
                max_items=8,
            ),
        ),
    ),
    SectionSpec(
        "home.steps",
        "home",
        "How to start",
        fields=(
            heading("মাত্র ৩ ধাপে শুরু করুন"),
            subtitle("ভর্তি থেকে প্রথম ক্লাস — কয়েক মিনিটেই।"),
            items(
                "steps",
                "Steps",
                [icon(), text("title", "Title", required=True), textarea("text", "Text")],
                [
                    {
                        "icon": "mouse-pointer-click",
                        "title": "কোর্স বেছে নিন",
                        "text": "শ্রেণি ও পছন্দমতো লাইভ বা রেকর্ডেড কোর্স দেখে নিন।",
                    },
                    {
                        "icon": "credit-card",
                        "title": "ভর্তি হন",
                        "text": "বিকাশ, নগদ, রকেট বা কার্ডে পেমেন্ট — সাথে সাথেই এক্সেস।",
                    },
                    {
                        "icon": "play-circle",
                        "title": "শেখা শুরু করুন",
                        "text": "ক্লাস দেখুন, নোট পড়ুন, পরীক্ষা দিন — অগ্রগতি দেখুন এক নজরে।",
                    },
                ],
                max_items=4,
            ),
        ),
    ),
    SectionSpec(
        "home.trust",
        "home",
        "Why trust us",
        fields=(
            heading("কেন আমাদের কোর্সে আস্থা রাখবেন?"),
            textarea(
                "text",
                "Text",
                "উপকরণ সবার কাছেই থাকে — পার্থক্য হয় পড়ানোর ধরনে। এখানে প্রতিটি টপিক পড়ানো হয় বুঝিয়ে, বোর্ড পরীক্ষাকে মাথায় রেখে।",
            ),
            items(
                "points",
                "Points",
                [text("text", "Point", required=True)],
                [
                    {"text": "সহজ ভাষায় কঠিন টপিক — মুখস্থ নয়, বুঝিয়ে"},
                    {"text": "বোর্ড প্রশ্ন এনালাইসিস করে পড়ানো"},
                    {"text": "শর্ট টেকনিক ও পরীক্ষার হলের কৌশল"},
                    {"text": "ভুল ধরিয়ে দেওয়া — শুধু উত্তর নয়, কেন ভুল সেটাও"},
                ],
                max_items=6,
            ),
            image(
                "image",
                "Photo",
                "https://rahad-ict.sgp1.digitaloceanspaces.com/pages/kgK8lRrSMHyTf9BPgkDsPqL6U1SEt2fR.jpg",
                required=True,
            ),
            text("image_label", "Name on the photo", "ICT with Rahad Sir"),
        ),
    ),
    SectionSpec(
        "home.instructors",
        "home",
        "Teachers",
        description="The teachers themselves are edited under Teachers. Also used on the About page.",
        fields=(heading("যাঁদের কাছে শিখবেন"), subtitle("প্রতিটি অধ্যায় পড়ান সেই বিষয়ের শিক্ষক — একজন সবকিছু নয়।")),
    ),
    SectionSpec(
        "home.testimonials",
        "home",
        "Student feedback",
        description="Shows approved feedback marked for the home page, edited under Feedback.",
        fields=(heading("শিক্ষার্থীদের অভিমত"), subtitle("যাঁরা এই ক্লাসগুলো করেছেন, তাঁদের নিজেদের কথায়।")),
    ),
    SectionSpec(
        "home.cta",
        "home",
        "Closing call to action",
        fields=(
            heading("আইসিটির প্রস্তুতি শুরু হোক আজই"),
            textarea("text", "Text", "কোন কোর্সটা আপনার জন্য ঠিক, বুঝতে পারছেন না? হোয়াটসঅ্যাপে জিজ্ঞেস করুন — আমরা সাহায্য করব।"),
            text("button_label", "Button", "সকল কোর্স দেখুন", required=True),
            link("button_link", "Button link", "/course", required=True),
            text("whatsapp_label", "WhatsApp button", "হোয়াটসঅ্যাপে প্রশ্ন করুন"),
        ),
    ),
    SectionSpec(
        "home.connect",
        "home",
        "Follow us",
        fields=(
            heading("যুক্ত হোন আমাদের সাথে"),
            subtitle("লাইভ ক্লাসের আপডেট, ফ্রি ক্লাস আর নোটিশ সবার আগে পেতে।"),
            items(
                "cards",
                "Links",
                [
                    choice("platform", "Platform", SOCIAL_PLATFORMS, "facebook"),
                    text("label", "Label", required=True),
                    text("cta", "Button", required=True),
                    link("link", "Link", required=True),
                ],
                [
                    {
                        "platform": "youtube",
                        "label": "আমাদের ফ্রি প্লে-লিস্ট",
                        "cta": "ভিডিও দেখুন",
                        "link": "https://www.youtube.com/@ictwithrahadsir",
                    },
                    {
                        "platform": "facebook",
                        "label": "অফিসিয়াল ফেইসবুক গ্রুপ",
                        "cta": "যুক্ত হোন",
                        "link": "https://www.facebook.com/groups/1929512690621460",
                    },
                    {
                        "platform": "instagram",
                        "label": "অফিসিয়াল ইন্সট্রাগ্রাম",
                        "cta": "ফলো করুন",
                        "link": "https://www.instagram.com/ict_with_rahad_sir/",
                    },
                    {
                        "platform": "facebook",
                        "label": "অফিসিয়াল ফেইসবুক পেজ",
                        "cta": "যুক্ত হোন",
                        "link": "https://www.facebook.com/rahadsir",
                    },
                ],
                max_items=6,
            ),
        ),
    ),
    SectionSpec(
        "app_download",
        "home",
        "Mobile app",
        description="Also shown on the notice page. The store link is under Brand & contact.",
        fields=(
            heading("আমাদের মোবাইল অ্যাপ ডাউনলোড করে আজই শেখা শুরু করুন!"),
            subtitle("প্রিমিয়াম কোর্সগুলো এক্সেস করুন যেকোনো সময়, যেকোনো জায়গায়"),
            image("image", "App preview", "https://www.ictwithrahadsir.com/images/google-play.jpg"),
        ),
    ),
)
