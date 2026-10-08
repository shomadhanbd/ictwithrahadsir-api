"""The About (পরিচিতি) page, top to bottom."""

from apps.website.registry.fields import SectionSpec, heading, icon, image, items, subtitle, text, textarea

SECTIONS = (
    SectionSpec(
        "about.hero",
        "about",
        "Hero",
        can_hide=False,
        fields=(
            text("title", "Heading", "আইসিটি-তে A+ — মুখস্থ নয়, বুঝে পড়ুন", required=True),
            textarea(
                "description",
                "Text",
                "এসএসসি ও এইচএসসি শিক্ষার্থীদের জন্য আইসিটির পূর্ণাঙ্গ প্রস্তুতি — সহজ ব্যাখ্যা, শর্ট টেকনিক আর "
                "বোর্ড প্রশ্নের নিয়মিত অনুশীলন।",
            ),
            items(
                "chips",
                "Tags",
                [text("text", "Tag", required=True)],
                [
                    {"text": "এসএসসি ও এইচএসসি আইসিটি"},
                    {"text": "লাইভ + রেকর্ডেড ক্লাস"},
                    {"text": "সিলেটে সেন্টার, সারাদেশে অনলাইন"},
                ],
                max_items=5,
            ),
            image(
                "image",
                "Photo",
                "https://rahad-ict.sgp1.digitaloceanspaces.com/pages/kgK8lRrSMHyTf9BPgkDsPqL6U1SEt2fR.jpg",
                required=True,
            ),
            text("image_label", "Name on the photo", "ICT with Rahad Sir"),
            text("button_label", "Button", "কোর্সগুলো দেখুন", required=True),
            text("whatsapp_label", "WhatsApp button", "হোয়াটসঅ্যাপে প্রশ্ন করুন"),
        ),
    ),
    SectionSpec(
        "about.story",
        "about",
        "Our story",
        fields=(
            heading("আমাদের কথা"),
            textarea(
                "body",
                "Story",
                "আইসিটি অনেক শিক্ষার্থীর কাছে ভয়ের বিষয় — বিশেষ করে সংখ্যা পদ্ধতি, প্রোগ্রামিং আর HTML। অথচ এটাই সবচেয়ে বেশি নম্বর "
                "তোলার বিষয় হতে পারে, যদি পড়ানোটা ঠিকভাবে হয়।\n\n"
                "ICT with Rahad Sir সেই লক্ষ্যেই তৈরি — প্রতিটি টপিক গোড়া থেকে বুঝিয়ে, বোর্ড প্রশ্নের ধরন ধরে অনুশীলন করিয়ে, "
                "শিক্ষার্থীকে পরীক্ষার হলে আত্মবিশ্বাসী করে তোলা।",
                required=True,
                help="Leave an empty line between paragraphs.",
            ),
            text("mission_heading", "Mission heading", "আমাদের লক্ষ্য"),
            textarea(
                "mission",
                "Mission",
                "প্রতিটি শিক্ষার্থী যেন আইসিটি বিষয়টা সত্যিকারভাবে বোঝে এবং আত্মবিশ্বাসের সাথে পরীক্ষা দিয়ে কাঙ্ক্ষিত ফলাফল অর্জন করে।",
            ),
        ),
    ),
    SectionSpec(
        "about.syllabus",
        "about",
        "What we teach",
        description="The chapters are edited under Home → Syllabus.",
        fields=(
            heading("কী পড়াই — এইচএসসি আইসিটির ৬টি অধ্যায়"),
            subtitle("পুরো সিলেবাস, অধ্যায় ধরে ধরে — যেসব টপিকে শিক্ষার্থীরা সবচেয়ে বেশি আটকে যায় সেগুলোতে বাড়তি জোর।"),
            text("marks_heading", "Marks heading", "পরীক্ষার নম্বর বণ্টন (মোট ১০০)"),
            items(
                "marks",
                "Marks",
                [text("label", "Part", required=True), text("value", "Marks", required=True)],
                [
                    {"label": "সৃজনশীল (CQ)", "value": "৫০"},
                    {"label": "বহুনির্বাচনি (MCQ)", "value": "২৫"},
                    {"label": "ব্যবহারিক", "value": "২৫"},
                ],
                max_items=4,
            ),
        ),
    ),
    SectionSpec(
        "about.method",
        "about",
        "How we teach",
        fields=(
            heading("কীভাবে পড়াই"),
            subtitle("প্রতিটি অধ্যায় এই চার ধাপে — বোঝা থেকে পরীক্ষার হল পর্যন্ত।"),
            items(
                "steps",
                "Steps",
                [text("title", "Title", required=True), textarea("text", "Text")],
                [
                    {"title": "কনসেপ্ট ক্লাস", "text": "প্রতিটি টপিক গোড়া থেকে, উদাহরণ দিয়ে — যেন মুখস্থ নয়, বোঝা হয়।"},
                    {"title": "শর্ট টেকনিক", "text": "সংখ্যা রূপান্তর, লজিক গেট আর প্রোগ্রামের আউটপুট দ্রুত বের করার কৌশল।"},
                    {"title": "বোর্ড প্রশ্ন সমাধান", "text": "বিগত বছরের সব বোর্ডের প্রশ্ন ধরে ধরে সমাধান ও উত্তর লেখার নিয়ম।"},
                    {"title": "পরীক্ষা ও র‍্যাঙ্কিং", "text": "অধ্যায় শেষে পরীক্ষা, মডেল টেস্ট আর র‍্যাঙ্কিং — নিজের অবস্থান জানুন।"},
                ],
                max_items=6,
            ),
            items(
                "benefits",
                "What students get",
                [icon(), text("title", "Title", required=True), textarea("text", "Text")],
                [
                    {
                        "icon": "play-circle",
                        "title": "লাইভ ক্লাস + রেকর্ডিং",
                        "text": "ক্লাস মিস হলেও চিন্তা নেই — রেকর্ডিং দেখে নিন যেকোনো সময়।",
                    },
                    {
                        "icon": "file-text",
                        "title": "লেকচার শিট ও নোট",
                        "text": "প্রতিটি অধ্যায়ের গোছানো নোট আর অনুশীলনী শিট।",
                    },
                    {
                        "icon": "clipboard-check",
                        "title": "অনলাইন পরীক্ষা",
                        "text": "MCQ-র ফল সাথে সাথে, সাথে ব্যাখ্যা ও সঠিক উত্তর।",
                    },
                    {
                        "icon": "pen-line",
                        "title": "সৃজনশীল খাতা মূল্যায়ন",
                        "text": "হাতে লেখা উত্তরের ছবি জমা দিন — শিক্ষক নম্বর দিয়ে মূল্যায়ন করবেন।",
                    },
                    {"icon": "bar-chart-3", "title": "অগ্রগতি ট্র্যাকিং", "text": "কোন লেসন শেষ, কোনটা বাকি — এক নজরে দেখুন।"},
                    {
                        "icon": "messages-square",
                        "title": "প্রশ্নোত্তর সাপোর্ট",
                        "text": "হোয়াটসঅ্যাপ ও ফেসবুক গ্রুপে প্রশ্ন করুন, উত্তর পাবেন।",
                    },
                ],
                max_items=9,
            ),
        ),
    ),
    SectionSpec(
        "about.audience",
        "about",
        "Who it is for",
        fields=(
            heading("কাদের জন্য"),
            items(
                "items",
                "Groups",
                [text("title", "Title", required=True), textarea("text", "Text")],
                [
                    {"title": "এইচএসসি শিক্ষার্থী", "text": "একাদশ ও দ্বাদশ — পুরো সিলেবাস, বোর্ড প্রস্তুতি ও মডেল টেস্ট।"},
                    {"title": "এসএসসি শিক্ষার্থী", "text": "নবম ও দশম — আইসিটির ভিত্তি মজবুত করুন শুরু থেকেই।"},
                    {"title": "যারা আইসিটিতে দুর্বল", "text": "প্রোগ্রামিং বা সংখ্যা পদ্ধতি কঠিন লাগে? একদম শুরু থেকে শিখুন।"},
                    {"title": "শেষ মুহূর্তের প্রস্তুতি", "text": "পরীক্ষার আগে দ্রুত রিভিশন আর গুরুত্বপূর্ণ প্রশ্নের অনুশীলন।"},
                ],
                max_items=8,
            ),
        ),
    ),
    SectionSpec(
        "about.faq",
        "about",
        "Questions & answers",
        fields=(
            heading("সাধারণ প্রশ্নোত্তর"),
            subtitle("আরও কিছু জানার থাকলে হোয়াটসঅ্যাপে সরাসরি প্রশ্ন করুন।"),
            items(
                "items",
                "Questions",
                [text("question", "Question", required=True), textarea("answer", "Answer", required=True)],
                [
                    {
                        "question": "অনলাইনে ক্লাস করতে কী লাগবে?",
                        "answer": "একটি মোবাইল, ট্যাব বা কম্পিউটার আর ইন্টারনেট সংযোগ — ব্যস। ক্লাস, নোট আর পরীক্ষা সব ওয়েবসাইটেই।",
                    },
                    {
                        "question": "লাইভ ক্লাস মিস করলে কী হবে?",
                        "answer": "প্রতিটি লাইভ ক্লাসের রেকর্ডিং কোর্সে যোগ হয়, পরে যেকোনো সময় দেখে নিতে পারবেন।",
                    },
                    {
                        "question": "প্রোগ্রামিং আগে কখনো করিনি — পারব?",
                        "answer": "অবশ্যই। একদম শুরু থেকে, সহজ উদাহরণ দিয়ে পড়ানো হয়। আগের কোনো অভিজ্ঞতা লাগে না।",
                    },
                    {
                        "question": "সৃজনশীল প্রশ্নের উত্তর কীভাবে জমা দেব?",
                        "answer": "পরীক্ষার সময় খাতায় লিখে প্রতিটি পৃষ্ঠার ছবি বা PDF আপলোড করবেন। "
                        "শিক্ষক মূল্যায়ন শেষে নম্বর ও নমুনা উত্তর "
                        "দেখতে পাবেন।",
                    },
                    {
                        "question": "পেমেন্ট কীভাবে করব?",
                        "answer": "বিকাশ, নগদ, রকেট বা কার্ডে অনলাইনে পেমেন্ট করা যায়। সেন্টারে এসে নগদেও ভর্তি হতে পারবেন।",
                    },
                    {
                        "question": "কোর্সের মেয়াদ শেষ হলে কী হবে?",
                        "answer": "মেয়াদ শেষের কয়েকদিন আগে SMS-এ জানানো হয়, তখন থেকেই মেয়াদ বাড়ানো যায় — "
                        "নতুন মেয়াদ আগেরটার শেষ থেকে "
                        "যোগ হয়।",
                    },
                ],
                max_items=20,
            ),
        ),
    ),
    SectionSpec(
        "about.cta",
        "about",
        "Closing call to action",
        fields=(
            heading("আইসিটির প্রস্তুতি শুরু হোক আজই"),
            textarea("text", "Text", "আপনার শ্রেণির কোর্স বেছে নিন, অথবা কোনটা আপনার জন্য সঠিক তা জানতে আমাদের সাথে কথা বলুন।"),
            text("button_label", "Button", "সকল কোর্স দেখুন", required=True),
        ),
    ),
    SectionSpec(
        "about.management",
        "about",
        "Management",
        description="Who runs the business, shown on About Us with the trade license details, as SSLCommerz requires.",
        fields=(
            heading("পরিচালনায়"),
            items(
                "people",
                "Person",
                [text("name", "Name", required=True), text("role", "Role"), image("photo", "Photo")],
                [],
                max_items=6,
            ),
        ),
    ),
    SectionSpec(
        "contact",
        "about",
        "Contact",
        description="Phone, WhatsApp, email and address come from Brand & contact.",
        fields=(
            heading("যোগাযোগ"),
            subtitle("যেকোনো প্রয়োজনে আমাদের সাথে যোগাযোগ করুন — দ্রুত উত্তরের জন্য হোয়াটসঅ্যাপই সবচেয়ে ভালো।"),
            text("whatsapp_hint", "WhatsApp note", "দ্রুত উত্তর পেতে"),
            text("facebook_hint", "Facebook group note", "ক্লাসের আপডেট ও আলোচনা"),
            text("email_hint", "Email note", "বিস্তারিত জানাতে"),
        ),
    ),
)
