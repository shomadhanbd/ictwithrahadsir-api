"""Sections every page uses: brand and contact details, and the footer."""

from apps.website.registry.fields import SectionSpec, email, image, link, text, textarea

SECTIONS = (
    SectionSpec(
        "site",
        "global",
        "Brand & contact",
        can_hide=False,
        description="Shown in the header, footer, contact page and browser tabs.",
        fields=(
            text("brand_name", "Brand name", "ICT with Rahad Sir", required=True),
            text("short_name", "Short name", "RAHAD ICT", required=True, help="Ends every browser-tab title."),
            image("logo", "Logo", "https://www.ictwithrahadsir.com/logo/rahat-logo.png", required=True),
            text("phone", "Phone", "+8801711778602", required=True),
            text("whatsapp", "WhatsApp number", "8801711778602", required=True, help="With 880, digits only."),
            email("email", "Email", "ictwithrahadsir@gmail.com", required=True),
            text("address", "Address", "চৌহাট্টা, সিলেট।", required=True),
            # SSLCommerz asks merchants to show these in the footer and on About Us.
            text("trade_license", "Trade license number", "1230050944", help="Shown in the footer and on About Us."),
            text("tin", "TIN number", help="Shown in the footer and on About Us once filled in."),
            text(
                "registered_address",
                "Registered address (trade license)",
                "চৌহাট্টা, সিলেট।",
                help="The address on the trade license.",
            ),
            text("support_hours", "Support hours", "সকাল ৯টা – রাত ৯টা"),
            text(
                "map_query",
                "Google Maps search",
                "Chouhatta, Sylhet, Bangladesh",
                help="Opens when a map link is clicked.",
            ),
            link(
                "map_embed_url",
                "Google Maps embed link",
                "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3618.7303030800726!2d91.8677462752115"
                "!3d24.89882267790886!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3751ab25390317e3"
                "%3A0x6b66804a1b021305!2sChouhatta%2C%20Sylhet!5e0!3m2!1sen!2sbd!4v1714213346513!5m2!1sen!2sbd",
                help="Google Maps → Share → Embed a map → copy the src link.",
            ),
            link("facebook_page", "Facebook page", "https://www.facebook.com/rahadsir"),
            link("facebook_group", "Facebook group", "https://www.facebook.com/groups/1929512690621460"),
            text("facebook_group_name", "Facebook group name", "ICT with Rahad Sir"),
            link("youtube", "YouTube", "https://www.youtube.com/@ictwithrahadsir"),
            link("instagram", "Instagram", "https://www.instagram.com/ict_with_rahad_sir/"),
            link(
                "play_store", "Google Play app", "https://play.google.com/store/apps/details?id=com.nextive.rahat_ict"
            ),
            text("payment_methods", "Payment methods", "বিকাশ, নগদ, রকেট ও কার্ডে পেমেন্ট"),
            image(
                "payment_badge",
                "Payment logos",
                "/images/sslcommerz-banner.png",
                help="SSLCommerz's current 'Pay with' banner, shown across the footer.",
            ),
            textarea(
                "seo_description",
                "Search description",
                "ICT with Rahad Sir is a educational platform that aims to help learners of all levels enhance "
                "their ICT skills and knowledge.",
                help="What search engines and link previews show for pages without their own.",
            ),
            image("og_image", "Link preview image", help="Shown when a page is shared on Facebook or WhatsApp."),
        ),
    ),
    SectionSpec(
        "footer",
        "global",
        "Footer",
        can_hide=False,
        fields=(
            textarea("tagline", "Tagline", "স্মার্ট প্রস্তুতির মাধ্যমে ICT -তে সেরা প্রস্তুতির এক নির্ভরযোগ্য শিক্ষাকেন্দ্র।"),
            text("help_title", "Help heading", "প্রশ্ন আছে? আমরা আছি।"),
            textarea("help_text", "Help text", "কোর্স, ভর্তি বা পেমেন্ট — যেকোনো বিষয়ে সকাল ৯টা থেকে রাত ৯টা পর্যন্ত।"),
        ),
    ),
)
