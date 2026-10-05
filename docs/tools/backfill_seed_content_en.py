"""回填种植日历 / 论坛版块 / 行业新闻的英文内容（第 72 批）

背景
----
第 69/72 批已解决"病害百科"内容数据的英文（name/crop_type/symptoms/description/防治措施）。
剩下三类**管理员维护的内容数据**此前完全没有英文字段，英文界面下整块是中文：

  · `CalendarTask.title` / `detail`（40 条通用农事模板，含 `crop_type`）
  · `ForumBoard.name` / `description`（3 个版块）
  · `News.title` / `content`（8 篇行业新闻）

本脚本按"中文原文"查表回填对应英文字段，幂等：只填空字段，
`--force` 可强制覆盖（会覆盖管理员已自行编辑的英文，慎用）。

用法：
    python docs/tools/backfill_seed_content_en.py
    python docs/tools/backfill_seed_content_en.py --force
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django  # noqa: E402

django.setup()

from api.models import News  # noqa: E402
from api.models_forum import ForumBoard  # noqa: E402
from api.models_calendar import CalendarTask  # noqa: E402

# ---------------------------------------------------------------- 作物名
CROPS = {
    '柑橘': 'Citrus',
    '玉米': 'Corn',
    '番茄': 'Tomato',
    '苹果': 'Apple',
    '草莓': 'Strawberry',
    '葡萄': 'Grape',
    '马铃薯': 'Potato',
}

# ---------------------------------------------------------------- 版块
BOARDS = {
    '作物病害交流': (
        'Crop Disease Discussion',
        'Share and discuss the symptoms and control methods of crop diseases',
    ),
    '种植技术': (
        'Growing Techniques',
        'Exchange crop growing experience and techniques',
    ),
    '农药肥料': (
        'Pesticides & Fertiliser',
        'Discuss experience with pesticides and fertilisers',
    ),
}

# ---------------------------------------------------------------- 农事任务
# 键为中文标题；仅"适期播种"在玉米/马铃薯两个作物下同名，用 (作物, 标题) 区分。
CALENDAR_BY_TITLE = {
    '春季修剪与清园': ('Spring pruning and orchard clean-up',
                 'Remove diseased and overcrowded branches; clean the orchard to reduce overwintering pest and disease sources.'),
    '春梢肥与红蜘蛛防治': ('Spring shoot fertiliser and spider mite control',
                  'Apply fertiliser to promote spring shoots; watch for spider mites and aphids.'),
    '幼果期防溃疡病': ('Prevent canker during the young fruit stage',
                'Prevent canker and gummosis at the young fruit stage; ensure good drainage.'),
    '稳果壮果肥': ('Fruit-setting and fruit-sizing fertiliser',
              'Apply fruit-sizing fertiliser, keep soil moisture even, and reduce fruit cracking.'),
    '分批采收': ('Staggered harvesting',
             'Harvest in batches according to ripeness and restore tree vigour with timely nutrition afterwards.'),
    '防冻与涂白': ('Frost protection and trunk whitewashing',
              'Irrigate before cold waves and whitewash the trunk; young trees can be covered for frost protection.'),
    '选种备耕': ('Seed selection and land preparation',
             'Choose disease-resistant varieties, plough deeply, and apply plenty of basal fertiliser.'),
    '适期播种': ('Sowing at the right time',
             'Sow once soil temperature has stabilised; watch for soil-dwelling pests.'),
    '拔节期追肥': ('Top-dressing at the jointing stage',
              'Apply nitrogen at the jointing stage and watch for corn borer.'),
    '大喇叭口期防叶斑病': ('Prevent leaf spots at the big flare stage',
                  'Focus on northern and southern leaf blight; ensure drainage after rain.'),
    '完熟期收获': ('Harvest at full maturity',
              'Harvest and dry promptly once the grain is fully ripe; return straw to the field or clear diseased residues.'),
    '温室育苗': ('Raising seedlings in the greenhouse',
             'Keep seedlings warm and ventilated to prevent damping-off; water sparingly and avoid waterlogged beds.'),
    '适期定植': ('Transplanting at the right time',
             'Transplant once soil temperature is steady above 12°C and apply well-rotted organic manure as basal fertiliser.'),
    '开花坐果期水肥': ('Water and fertiliser at flowering and fruit set',
                'Apply potassium after fruit set, avoid flood irrigation, and ventilate to lower humidity and prevent grey mould.'),
    '及时采收与整枝': ('Timely harvest and pruning',
                'Harvest in batches as fruit colours, and remove lower old leaves and side shoots to improve airflow.'),
    '秋茬育苗': ('Raising seedlings for the autumn crop',
             'Raise seedlings under shade to keep them cool; watch for aphids and viral diseases.'),
    '大棚防晚疫病': ('Prevent late blight in the greenhouse',
               'Keep warm at night and ventilate by day to remove moisture; remove infected plants promptly.'),
    '越冬茬管理': ('Managing the overwintering crop',
              'Improve insulation, water less often, and focus on late blight and grey mould during cold, humid spells.'),
    '萌芽前修剪与清园': ('Pruning and orchard clean-up before bud break',
                 'Finish winter pruning and remove diseased branches, fallen leaves and mummified fruit to reduce primary inoculum.'),
    '花前预防黑星病': ('Prevent apple scab before flowering',
                'Spray before flowering to prevent apple scab and ring rot; protect natural enemies.'),
    '幼果期追肥与疏果': ('Top-dressing and fruit thinning at the young fruit stage',
                 'Thin diseased and misshapen fruit, apply fruit-sizing fertiliser, and keep soil moisture steady.'),
    '雨季防黑星病与炭疽病': ('Prevent apple scab and bitter rot in the rainy season',
                   'Apply a protective fungicide before the rains and re-spray promptly afterwards.'),
    '分批采收与秋施基肥': ('Staggered harvest and autumn basal fertiliser',
                  'Harvest in batches according to ripeness and apply organic fertiliser early after harvest to restore tree vigour.'),
    '落叶后清园与涂白': ('Clean-up and trunk whitewashing after leaf fall',
                 'Sweep up fallen leaves and diseased fruit; whitewash the trunk against frost and sunscald.'),
    '花果期水肥管理': ('Water and fertiliser during flowering and fruiting',
                'Apply light, frequent fertiliser during flowering and fruiting and keep greenhouse humidity from getting too high.'),
    '结果后期防白粉病': ('Prevent powdery mildew late in the fruiting period',
                 'Late in the fruiting period focus on powdery mildew and leaf scorch; remove diseased and old leaves promptly.'),
    '整地施基肥': ('Land preparation and basal fertiliser',
              'Plough deeply, apply plenty of organic fertiliser, and form raised beds.'),
    '覆膜保温': ('Mulching for insulation',
             'Cover the greenhouse with film to retain heat and ventilate to lower humidity and prevent grey mould.'),
    '出土上架与清园': ('Uncovering, trellising and orchard clean-up',
                'Remove the winter soil cover, tie the vines onto the trellis, and clear diseased residues.'),
    '花前花后防霜霉病': ('Prevent downy mildew before and after flowering',
                 'Spray once before and once after flowering against downy mildew and grey mould, and ventilate the greenhouse.'),
    '膨果期水肥与控梢': ('Water, fertiliser and shoot control during berry enlargement',
                 'Apply potassium to promote berry enlargement, control excessive shoot growth, and pinch tips promptly.'),
    '转色期防霜霉病与白腐病': ('Prevent downy mildew and white rot at veraison',
                   'Limit water at veraison and focus on downy mildew and white rot.'),
    '适期采收': ('Harvesting at the right time',
             'Harvest at the right ripeness for each variety and keep the leaves healthy afterwards to restore vigour.'),
    '修剪与埋土防寒': ('Pruning and burying vines for winter protection',
                'Clean the vineyard after winter pruning; in northern regions bury the vines against the cold.'),
    '种薯切块催芽': ('Cutting seed potatoes and sprouting',
              'Cut the tubers, let the wounds dry and disinfect them, then sprout once soil temperature rises.'),
    '现蕾期防晚疫病': ('Prevent late blight at the budding stage',
               'Begin late blight prevention at the budding stage, combined with earthing up.'),
    '块茎膨大期水肥': ('Water and fertiliser during tuber enlargement',
                'Keep water available during tuber enlargement and avoid alternating drought and waterlogging.'),
    '茎叶枯黄后收获': ('Harvest after the haulm turns yellow',
               'Harvest promptly once the haulm yellows and stop irrigation a week before harvest.'),
}

# 同名的"适期播种"按作物区分
CALENDAR_BY_CROP_TITLE = {
    ('马铃薯', '适期播种'): ('Sowing at the right time',
                      'Sow at the right time, control soil-dwelling pests, and avoid continuous cropping.'),
}


# ---------------------------------------------------------------- 新闻
# ---------------------------------------------------------------- 新闻来源机构
NEWS_SOURCES = {
    '中国气象局': 'China Meteorological Administration',
    '全国农业技术推广服务中心': 'National Agricultural Technology Extension and Service Centre',
    '农业农村部农产品质量安全监管司':
        'Department of Agricultural Product Quality and Safety Supervision, MARA',
    '农业农村部农田建设管理司': 'Department of Farmland Construction and Management, MARA',
    '农业农村部市场与信息化司': 'Department of Market and Information Technology, MARA',
    '农业农村部政策与改革司': 'Department of Policy and Reform, MARA',
    '农业农村部渔业渔政管理局': 'Bureau of Fisheries, MARA',
}


def _news(content_id):
    return NEWS.get(content_id, ('', ''))


NEWS = {
    # ---- 12: 全国农业气象周报 ----
    12: (
        'National agricultural meteorological weekly report',
        'National Agricultural Meteorological Weekly Report\n'
        '(4–10 June 2023)\n\n'
        '1. Overview of the week\u2019s weather and its impact on agriculture\n'
        'During the week of 4–10 June 2023, light and heat conditions were normal across most agricultural '
        'regions, rainfall was generally well distributed and soil moisture was good, so weather conditions were '
        'broadly favourable for the growth and yield formation of autumn-harvested crops. Most of the Northeast, '
        'North China and the Huang-Huai region saw clear weather with suitable soil moisture, favouring grain '
        'filling in corn and soybean. Most of the south had frequent showers, which effectively replenished '
        'reservoirs and ponds and benefited single-season rice and summer corn. In the Southwest, overly wet soil '
        'was relieved in some fields and crop growth gradually recovered.\n\n'
        '2. Regional analysis of agrometeorological conditions\n'
        'Northeast: normal light and temperature with suitable soil moisture, generally favouring grain filling '
        'and seed setting in corn, rice and soybean.\n\n'
        'North China and Huang-Huai: clear weather, abundant sunshine and moderate soil moisture, favourable for '
        'tasselling and silking in summer corn and for boll growth in cotton.\n\n'
        'South: mostly scattered rainfall. Parts of Jiangnan and South China saw short spells of heavy rain, but '
        'the overall impact on agriculture was limited and the growing environment for rice, fruit and vegetables '
        'remained good.\n\n'
        'Southwest: rainfall decreased, the extent of overly wet soil shrank, light and temperature conditions '
        'improved, and the meteorological risk of crop pests and diseases was low.\n\n'
        '3. Agrometeorological outlook and recommendations\n'
        'Over the coming week, agricultural regions in the north are expected to remain clear or partly cloudy '
        'while rainfall increases in the south. All regions are advised to watch the weather closely:\n\n'
        'The Northeast should fertilise in good time to promote grain filling and guard against early frost;\n\n'
        'North China and Huang-Huai should strengthen field water and nutrient management for autumn grain crops;\n\n'
        'The south should drain waterlogged fields after heavy rain and monitor and control rice pests and diseases.\n\n'
        '4. Conclusion\n'
        'Agrometeorological conditions nationwide were generally good this week and no large-scale agrometeorological '
        'disaster occurred. The weather is expected to remain broadly favourable for crop growth in most regions, and '
        'all areas are advised to strengthen field management in line with local conditions.'
    ),
    # ---- 16: 农产品质量安全监测情况通报 ----
    16: (
        'Bulletin on the monitoring of agricultural product quality and safety',
        'In the second quarter of 2023, the Department of Agricultural Product Quality and Safety Supervision of the '
        'Ministry of Agriculture and Rural Affairs organised routine nationwide monitoring of agricultural product '
        'quality and safety. The results show an overall pass rate of 97.8%, up 0.2 percentage points year on year, '
        'with quality and safety levels remaining stable and improving.\n\n'
        '1. Basic information on the monitoring\n'
        'This round covered 31 provinces (autonomous regions and municipalities) and the Xinjiang Production and '
        'Construction Corps, focusing on vegetables, fruit, livestock and poultry products and aquatic products. '
        'Nearly 50,000 batches were sampled across production, purchasing, transport and slaughter, and more than '
        '80 indicators were tested, including pesticide residues, veterinary drug residues, heavy metal '
        'contamination and illegal additives.\n\n'
        '2. Analysis of the results\n'
        'The pass rate for vegetables was 98.1%, up 0.3 percentage points year on year; root and tuber vegetables, '
        'leafy vegetables and cucurbits performed particularly well.\n\n'
        '1. The pass rate for fruit was 97.5%, essentially flat year on year. Staple fruits such as peach, apple and '
        'citrus remained stable.\n\n'
        '2. The pass rate for livestock and poultry products was 98.0%, up 0.1 percentage points year on year. Pork, '
        'poultry meat and eggs all met national standards.\n\n'
        '3. The pass rate for aquatic products was 96.9%, a slight year-on-year improvement. Fish, shrimp, crab and '
        'shellfish were generally in good condition.\n\n'
        '4. The main problems found were pesticide and veterinary drug residues exceeding limits in a small number '
        'of products, and non-standard use of agricultural inputs in some areas. The Ministry has instructed the '
        'regions concerned to investigate and prosecute in accordance with the law and has guided producers to '
        'rectify the issues.\n\n'
        '3. Priorities for the next stage\n'
        'The Ministry of Agriculture and Rural Affairs will continue to strengthen supervision of agricultural '
        'product quality and safety, push forward territorial responsibilities and the primary responsibilities of '
        'producers and operators, and reinforce source control and process management. It will also increase the '
        'intensity and frequency of monitoring and deepen risk assessment and early warning mechanisms to safeguard '
        'food safety.\n\n'
        'Hereby notified.\n\n'
        'Department of Agricultural Product Quality and Safety Supervision,\n'
        'Ministry of Agriculture and Rural Affairs\n'
        '26 July 2023'
    ),
    # ---- 17: 信贷担保支持政策 ----
    17: (
        'Ministry of Agriculture and Rural Affairs introduces credit guarantee support for new agricultural '
        'business entities, widening coverage and lowering financing costs',
        'The Ministry of Agriculture and Rural Affairs and the Ministry of Finance have jointly issued the Notice on '
        'Further Improving Credit Guarantee Services for New Agricultural Business Entities, setting out a range of '
        'support measures to address the difficulty and cost of financing for family farms, farmer cooperatives and '
        'similar entities. To help agricultural business entities and relevant organisations understand the policy '
        'accurately, it is interpreted below:\n\n'
        '1. Background and objectives\n'
        'As agricultural modernisation accelerates, new agricultural business entities such as family farms and '
        'farmer cooperatives have gradually become an important force in safeguarding national food security and the '
        'supply of major agricultural products. However, many still face high credit thresholds and costly '
        'financing. This policy aims to ease the funding bottleneck in agricultural development by strengthening '
        'guarantee support, widening coverage and improving service processes.\n\n'
        '2. Main content\n'
        'Widening the range of guaranteed borrowers:\n'
        'Building on the existing policy, large-scale livestock and aquaculture farms, agricultural service '
        'organisations and large grain growers are brought into the scope of guarantee support so that more entities '
        'benefit.\n\n'
        'Raising credit loan ceilings and lowering overall financing costs:\n'
        'Eligible entities are offered credit guarantees with a per-household credit ceiling raised to 3 million yuan, '
        'and guarantee fees are explicitly capped at 0.8% in principle, genuinely reducing the burden on entities.\n\n'
        'Simplifying approval and promoting online services:\n'
        'The national agricultural credit guarantee system is supported in adopting digital services and one-click '
        'loan applications to shorten approval times and improve financing efficiency.\n\n'
        'Establishing a risk compensation mechanism:\n'
        'Where objective factors such as natural disasters or market fluctuations raise loan risk, central and local '
        'finances will share risk compensation, strengthening banks\u2019 confidence to lend.\n\n'
        '3. Significance and impact\n'
        'By combining fiscal and financial efforts, the policy not only helps solve the financing difficulties of '
        'agricultural business entities but also demonstrates the state\u2019s determination to channel financial '
        'resources towards agriculture. It is significant for consolidating poverty alleviation gains, advancing '
        'rural industrial revitalisation and improving the agricultural support and protection system.\n\n'
        '4. Next steps\n'
        'The Ministry of Agriculture and Rural Affairs, together with relevant departments, will push for rapid '
        'implementation, continue to improve the agricultural credit guarantee service network, and strengthen '
        'policy communication and training so that new agricultural business entities can genuinely understand, '
        'use and obtain these loans.'
    ),
    # ---- 20: 水产健康养殖示范区 ----
    20: (
        'Notice on the 2023 creation of national demonstration zones for healthy and ecological aquaculture',
        'To the agriculture (fisheries) departments (bureaux, committees) of all provinces, autonomous regions and '
        'municipalities, and the Agriculture and Rural Affairs Bureau of the Xinjiang Production and Construction '
        'Corps:\n\n'
        'To implement the requirements of the Notice of the Ministry of Agriculture and Rural Affairs on the "Five '
        'Major Actions" for extending green and healthy aquaculture technology, and to vigorously develop ecological '
        'and healthy aquaculture, the Ministry has decided to continue the 2023 creation of national demonstration '
        'zones for healthy and ecological aquaculture (hereafter "demonstration zones"). The relevant matters are '
        'notified as follows:\n\n'
        '1. Objectives\n'
        'Around the green and high-quality development of aquaculture, a further group of demonstration zones will '
        'be added that put the idea that "lucid waters and lush mountains are invaluable assets" into practice, '
        'playing a leading role in standardised management, green development and industrial integration.\n\n'
        '2. Eligible applicants\n'
        'Demonstration zones may be created by production and operating units, farmer professional cooperatives or '
        'county-level people\u2019s governments.\n\n'
        '3. Work arrangements\n\n'
        'Application period: 1 August to 15 September 2023.\n\n'
        'Application procedure: applicants voluntarily apply to the county-level fisheries authority; after review '
        'and recommendation by the municipal and then provincial authorities, materials are submitted to the '
        'Ministry.\n\n'
        'Assessment and acceptance: in the fourth quarter the Ministry will organise expert review and on-site '
        'spot checks, and will publicise and name the demonstration zones that meet the standards.\n\n'
        '4. Contact\n'
        '12345678\n\n'
        'All regions are asked to attach great importance to this work, organise it carefully, recommend the best '
        'candidates and submit materials on time.\n\n'
        'Hereby notified.'
    ),
    # ---- 21: 生猪价格 ----
    21: (
        'Tighter supply and demand: hog prices rebound from the bottom and stabilise',
        'According to monitoring data from the Ministry of Agriculture and Rural Affairs, by late July the national '
        'average farm-gate price of live pigs was 16.5 yuan per kilogram, up 15.4% month on month — a marked rebound '
        'after many months at low levels, with the market moving towards a new supply-demand balance.\n\n'
        'Features of the market this period:\n\n'
        'Supply contraction: after a prolonged slump in hog prices the industry fell into deep losses, farmers became '
        'less willing to hold animals back, and the clearing of heavy pigs accelerated. At the same time, the breeding '
        'sow herd has fallen for several consecutive months, feeding through to a temporary reduction in current '
        'supply.\n\n'
        'Demand recovery: with the summer consumption peak, outdoor dining increased, and the state\u2019s launch of '
        'pork reserve purchases sent a positive signal that effectively lifted market confidence.\n\n'
        'Outlook: analysts consider that prices have now recovered above the cost line for most producers and that '
        'industry losses have eased. In the short term hog prices are expected to stabilise with some fluctuation. '
        'Farms are advised to plan production sensibly, keep to a normal marketing rhythm, and avoid holding animals '
        'back in the hope of a lucky market.'
    ),
    # ---- 22: 水稻两迁害虫 ----
    22: (
        'Ministry of Agriculture and Rural Affairs promotes new green control technology for rice\u2019s "two '
        'migrants" pests',
        'The National Agricultural Technology Extension and Service Centre recently held a field demonstration of '
        'green control technology for rice pests and diseases in Changsha, Hunan, highlighting a new green control '
        'technology for the brown planthopper and the rice leaf folder (the "two migrants"). The technology is '
        'expected to cut chemical pesticide use significantly while safeguarding rice quality and the ecological '
        'environment.\n\n'
        'The technology centres on "one trap, one refuge, one protection":\n\n'
        '"One trap": widely deploy new sex-pheromone traps and insecticidal lamps to precisely kill adults and reduce '
        'egg laying in the field.\n\n'
        '"One refuge": plant flowering species such as vetiver grass and sesame along field edges to harbour natural '
        'enemies, providing habitat and alternative prey for spiders and Trichogramma wasps and strengthening '
        'ecological pest control.\n\n'
        '"One protection": scientifically select high-efficiency, low-toxicity, low-residue biopesticides and spray '
        'adjuvants, and apply them precisely at key control windows to protect the paddy ecosystem as far as '
        'possible.\n\n'
        'It is reported that in demonstration plots in Hunan and Jiangxi the technology achieved over 90% control of '
        'the "two migrants" while cutting chemical pesticide use by more than 30%, delivering both economic and '
        'ecological benefits. Agronomists recommend that rice-growing regions adapt and extend the technology to '
        'local conditions.'
    ),
    # ---- 25 / 27: 耕地保护（两篇内容相同，是历史遗留的重复数据） ----
    25: (
        'Policy interpretation of the Farmland Protection and Quality Improvement Project Implementation Plan: '
        'shoring up the foundation of food security and advancing sustainable agriculture',
        'The Ministry of Agriculture and Rural Affairs, together with the Ministry of Finance and the Ministry of '
        'Natural Resources, has issued the Farmland Protection and Quality Improvement Project Implementation Plan '
        '(2023\u20132025) (hereafter "the Plan"), setting out the objectives, key tasks and support policies for '
        'farmland protection and soil fertility improvement over the next three years. To help relevant departments '
        'and new agricultural business entities understand and implement it accurately, the main points are '
        'interpreted below:\n'
        '1. Background and significance\n'
        'Farmland is the "lifeblood" of grain production. Some regions still face degraded farmland quality, soil '
        'pollution and insufficient organic matter, which constrain further gains in overall agricultural production '
        'capacity. The Plan is a key measure for implementing the strategy of "storing grain in the land and in '
        'technology", intended to raise farmland quality through systematic engineering and policy support, shore up '
        'the foundation of national food security and promote green, high-quality and efficient agricultural '
        'development.\n'
        '2. Core policy content\n'
        'A dual goal of "improving quality and safeguarding quantity":\n'
        'The Plan proposes that by 2025 the cumulative area of high-standard farmland should reach 1.2 billion mu, '
        'the average farmland quality grade should rise by 0.1, soil organic matter should increase steadily, and '
        'more than 60% of degraded farmland in key regions should be remediated.\n'
        'Three key actions:\n'
        'Remediating degraded farmland: focus on saline-alkali land in the north and acidified farmland in the '
        'south, extending soil conditioning, biological improvement and similar technical models.\n'
        'Raising organic matter: encourage straw return, green manure crops and increased organic fertiliser, and '
        'build a long-term farmland quality monitoring network.\n'
        'Maintaining farmland infrastructure: improve maintenance mechanisms for irrigation, roads and power grids '
        'in already-built high-standard farmland.\n'
        'Strengthening funding and institutional safeguards:\n'
        'Central finance will continue to support this through agriculture-related transfer payments, applying a '
        '"major programme plus task list" management model and encouraging local governments to pool funds and '
        'attract social capital. A farmland quality assessment mechanism will also be established, incorporating '
        'project outcomes into the food security responsibility assessment.\n'
        '3. Highlights of the policy\n'
        'Greater emphasis on scientific and technological support: a set of key technologies for farmland '
        'conservation and restoration will be extended, and a precise "one area, one plan" remediation model will be '
        'established.\n'
        'Highlighting the role of farmers: family farms and cooperatives are encouraged to take on project tasks, '
        'with subsidies for related services and technical equipment.\n'
        'Emphasis on continuous tracking and evaluation: a "farmland quality big data platform" will support '
        'information-based management of the whole project cycle, ensuring results are quantifiable and assessable.\n'
        '4. Expected impact and recommendations\n'
        'Implementing the Plan will significantly strengthen the ecological resilience and overall productivity of '
        'farmland and support coordinated development of grain production with resource and environmental '
        'protection. Agriculture and rural affairs departments at all levels are advised to strengthen policy '
        'communication and training and to prepare local implementation plans quickly; growers and agricultural '
        'service organisations can follow project application information and adopt new technologies such as water '
        'saving and fertility building to take part in farmland protection.'
    ),
}
# 27 与 25 内容完全相同（历史重复数据），复用同一份英文
NEWS[27] = NEWS[25]


def main():
    force = '--force' in sys.argv

    # ---- 作物：优先用百科里已有的 crop_type → crop_type_en 映射 ----
    from api.models import PestInfo

    crop_map = dict(CROPS)
    for crop, crop_en in PestInfo.objects.exclude(crop_type_en='').values_list('crop_type', 'crop_type_en'):
        crop_map.setdefault(crop, crop_en)

    # ---- 日历 ----
    cal_done = 0
    cal_missing = []
    for task in CalendarTask.objects.all():
        pair = CALENDAR_BY_CROP_TITLE.get((task.crop_type, task.title)) or CALENDAR_BY_TITLE.get(task.title)
        if not pair:
            cal_missing.append(f'{task.crop_type}/{task.title}')
            continue
        title_en, detail_en = pair
        fields = []
        if force or not task.title_en:
            task.title_en = title_en
            fields.append('title_en')
        if force or not task.detail_en:
            task.detail_en = detail_en
            fields.append('detail_en')
        if fields:
            task.save(update_fields=fields)
            cal_done += 1

    # ---- 版块 ----
    board_done = 0
    for board in ForumBoard.objects.all():
        pair = BOARDS.get(board.name)
        if not pair:
            continue
        name_en, desc_en = pair
        fields = []
        if force or not board.name_en:
            board.name_en = name_en
            fields.append('name_en')
        if force or not board.description_en:
            board.description_en = desc_en
            fields.append('description_en')
        if fields:
            board.save(update_fields=fields)
            board_done += 1

    # ---- 新闻 ----
    news_done = 0
    news_missing = []
    for article in News.objects.all():
        pair = NEWS.get(article.id)
        if not pair:
            news_missing.append(article.id)
            continue
        title_en, content_en = pair
        fields = []
        if force or not article.title_en:
            article.title_en = title_en
            fields.append('title_en')
        if force or not article.content_en:
            article.content_en = content_en
            fields.append('content_en')
        source_en = NEWS_SOURCES.get(article.source or '')
        if source_en and (force or not article.source_en):
            article.source_en = source_en
            fields.append('source_en')
        if fields:
            article.save(update_fields=fields)
            news_done += 1

    print(f'日历任务：回填 {cal_done} 条，仍缺英文 {CalendarTask.objects.filter(title_en="").count()} 条')
    print(f'论坛版块：回填 {board_done} 条，仍缺英文 {ForumBoard.objects.filter(name_en="").count()} 条')
    print(f'行业新闻：回填 {news_done} 篇，仍缺英文 {News.objects.filter(title_en="").count()} 篇')
    if cal_missing:
        print('以下日历任务没有对应译文：')
        for item in cal_missing:
            print('  -', item)
    if news_missing:
        print('以下新闻没有对应译文（id）：', news_missing)


if __name__ == '__main__':
    main()
