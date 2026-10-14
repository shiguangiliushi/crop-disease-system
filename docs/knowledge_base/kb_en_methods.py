# -*- coding: utf-8 -*-
"""130 条防治措施的英文（译自校准版中文，勿增删信息）。

Keys are (pest_identifier, category); one entry per disease and category.
Translation policy:
  * nothing added and nothing dropped: no pesticide, rate, dose or practice
    appears here that is not in the calibrated Chinese source;
  * every number (dilution, PHI, spray interval, seasonal maximum, product
    content, Baume degree) is carried over unchanged;
  * every negative statement in the source (discontinued, restricted,
    not recommended) stays negative in English;
  * no Chinese characters anywhere in the values.
"""

EN = {
    # ------------------------------------------------------------------
    # apple_scab -- apple scab
    # ------------------------------------------------------------------
    ("apple_scab", "AGRICULTURAL"): (
        "1) Enforce strict quarantine: nursery stock and scion wood from affected areas must never be "
        "shipped out, and new plantings must not be established with stock from infested regions. "
        "2) In late autumn and early winter sweep up all fallen leaves and pick off mummified fruit from "
        "the trees; burn or bury the material deeper than 50 cm; the orchard floor may be sprayed with "
        "0.5% sodium dinitro-o-cresolate or 4:4:100 Bordeaux mixture to kill ascospores in the fallen "
        "leaves. 3) Prune in all four seasons (bud rubbing in spring, thinning of shoots in summer, "
        "removal of large limbs in autumn), thin out excessively dense branches, improve airflow and "
        "light in the canopy and shorten leaf wetness duration. 4) Apply more organic manure and the "
        "secondary and trace elements phosphorus, calcium, magnesium, boron and zinc; avoid excessive "
        "nitrogen; build tree vigour. 5) For new plantings choose relatively tolerant varieties."
    ),
    ("apple_scab", "CHEMICAL"): (
        "Pink bud and petal fall are the key timings, so shorten the gap between the pink-bud orchard "
        "clean-up spray and the first post-bloom spray. 1) Dormant period (before budbreak): spray "
        "3-5 °Bé lime sulphur to eradicate overwintering inoculum. 2) From pink bud to petal "
        "fall: spray 200 g/L pydiflumetofen + difenoconazole suspension concentrate (75 g/L "
        "pydiflumetofen + 125 g/L difenoconazole), 75% trifloxystrobin + tebuconazole water-dispersible "
        "granules, or 10% difenoconazole water-dispersible granules at 1500-2000x, 430 g/L tebuconazole "
        "suspension concentrate at 3000-4000x or 70% mancozeb wettable powder at 600-800x dilution, "
        "sprayed evenly over the whole orchard. 3) Depending on rainfall and disease pressure, spray "
        "every 7-10 days for 2-4 consecutive applications. 4) Rotate triazoles with strobilurins and "
        "EBDC fungicides to delay resistance. 5) On apple the pre-harvest interval for triazoles such as "
        "difenoconazole is generally 14-21 days, with no more than 4 applications per season; follow the "
        "label strictly."
    ),
    ("apple_scab", "ECOLOGICAL"): (
        "1) Sow natural grass between the rows or plant white clover or hairy vetch to improve the "
        "microclimate, shorten the duration of leaf wetness and increase populations of antagonistic "
        "microorganisms. 2) Apply microbial agents such as Trichoderma and Bacillus to improve the "
        "rhizosphere and phyllosphere microecology. 3) Protect natural enemies such as ladybirds, "
        "lacewings and parasitic wasps, and avoid broad-spectrum insecticides and fungicides. "
        "4) Reduce chemical fertiliser inputs and apply more bio-organic fertiliser to build soil "
        "fertility."
    ),
    ("apple_scab", "MONITORING"): (
        "1) From petal fall, survey marked trees and marked branches for the percentage of diseased "
        "leaves; start fungicide control as soon as the percentage of diseased leaves reaches 5% or the "
        "first infection lesion appears. 2) Use a spore trap together with rainfall and leaf wetness "
        "duration to predict ascospore release and infection peaks; after rain ends, use the "
        "Leader-Mills system to decide whether a protectant spray is needed. 3) Set up systematic "
        "observation plots to guide well-timed control for the whole orchard. 4) Near maturity, focus on "
        "checking fruit for lesions in order to decide the harvest and fruit bagging strategy."
    ),
    ("apple_scab", "PHYSICAL"): (
        "1) In autumn and winter, sweep up fallen leaves by hand, pick off mummified fruit from the "
        "trees and dispose of the material centrally. 2) Bag the fruit to block infection of the fruit. "
        "3) In protected or dwarfing orchards improve ventilation and lower humidity inside the canopy. "
        "4) In early spring till the tree basin to bury diseased leaves in the soil."
    ),
    # ------------------------------------------------------------------
    # apple_black_rot -- black rot
    # ------------------------------------------------------------------
    ("apple_black_rot", "AGRICULTURAL"): (
        "1) During dormant-season pruning (in the severe cold of February-March) cut out mummified fruit, "
        "dead branches, cankered limbs, fire blight-killed branches and remaining stubs completely, and "
        "burn or deep-bury them to reduce primary inoculum. 2) Do not leave dead stubs on the tree; paint "
        "saw cuts with a wound sealant. 3) Strengthen fertilisation and irrigation management to build "
        "tree vigour and prevent drought and waterlogging. 4) Control other diseases such as fire blight "
        "and Valsa canker to reduce dead wood and wounds. 5) Avoid mechanical injury to the fruit and "
        "harvest at the proper time when the fruit is mature."
    ),
    ("apple_black_rot", "CHEMICAL"): (
        "1) Apply 3-5 °Bé lime sulphur or 45% amobam aqueous solution in the dormant period to "
        "eradicate inoculum on the trunk and limbs. 2) In the growing season rely mainly on protectant "
        "fungicides: before bloom, after petal fall, during fruit enlargement and near maturity spray "
        "70% mancozeb wettable powder at 600-800x, 77% copper hydroxide wettable powder at 800x or 50% "
        "captan wettable powder at 600x. 3) At the first sign of disease or after rain spray systemic "
        "curative fungicides such as 10% difenoconazole water-dispersible granules at 1500-2000x or 25% "
        "prochloraz emulsifiable concentrate at 1000-1500x, alternating with protectants. 4) Trunk and "
        "limb cankers may be scraped out in spring and then painted with 45% amobam or a tebuconazole "
        "paste. 5) Follow the label pre-harvest interval strictly; the pre-harvest interval for captan on "
        "apple is generally 14 days."
    ),
    ("apple_black_rot", "ECOLOGICAL"): (
        "1) Grow grass between the rows to improve the microclimate and reduce rain splash. 2) Apply "
        "biocontrol agents such as Bacillus and Trichoderma to suppress pathogens on the limbs and "
        "around the leaves. 3) Protect natural enemies such as parasitic wasps, ladybirds and hoverflies, "
        "which also control insect vectors. 4) Apply more bio-organic fertiliser and humic acid to improve "
        "the rhizosphere microecology."
    ),
    ("apple_black_rot", "MONITORING"): (
        "1) Patrol the orchard regularly through the growing season for limb cankers and mummified fruit "
        "on the trees and prune them out promptly. 2) Near maturity (4-6 weeks before harvest) check the "
        "percentage of diseased fruit once a week, and pay extra attention to disease development after "
        "rain. 3) Combine spore trapping with rainfall forecasts to predict infection peaks. 4) In the "
        "1-2 years after an outbreak of fire blight, monitor closely for secondary black rot."
    ),
    ("apple_black_rot", "PHYSICAL"): (
        "1) In autumn and winter remove every mummified fruit from the trees, prune out diseased and dead "
        "branches, and take them out of the orchard for disposal. 2) In spring scrape out limb and trunk "
        "cankers (scraping the diseased bark clean to healthy tissue 0.5 cm beyond the edge of the "
        "sapwood) and then paint the wound for protection. 3) Bag the fruit to protect it. 4) Avoid "
        "pruning in the rain, which creates wounds. 5) For new plantings avoid low-lying, easily "
        "waterlogged or frost-prone sites."
    ),
    # ------------------------------------------------------------------
    # apple_cedar_apple_rust -- cedar apple rust
    # ------------------------------------------------------------------
    ("apple_cedar_apple_rust", "AGRICULTURAL"): (
        "1) Do not plant junipers, Chinese juniper or other alternate hosts within 0.5-1 km of a new "
        "orchard; in commercial orchards remove wild susceptible junipers within the basidiospore "
        "dispersal range of 3-5 km. 2) Choose resistant varieties: Red Delicious, Empire, Liberty, "
        "McIntosh and Spartan are relatively resistant, while Rome, Jonathan and Golden Delicious are "
        "susceptible. 3) Strengthen orchard management and apply more phosphate and potash fertiliser to "
        "build tree vigour."
    ),
    ("apple_cedar_apple_rust", "CHEMICAL"): (
        "1) On apple begin spraying at pink bud and finish about 14 days after petal fall: the first "
        "spray at pink bud, the second after petal fall, and in severely affected orchards a third "
        "spray 10-15 days after petal fall. 2) Commonly used products: 15% triadimefon wettable powder "
        "at 1500-2000x, 12.5% diniconazole wettable powder at 2000-2500x, 10% difenoconazole "
        "water-dispersible granules at 1500-2000x and 43% tebuconazole suspension concentrate at 3000x. "
        "3) Rotate triazoles with protectant mancozeb to avoid resistance. 4) On juniper, before "
        "budbreak in spring, spray 3-5 °Bé lime sulphur or 15% triadimefon wettable powder at "
        "1000x to reduce telial horn production. 5) Follow the label pre-harvest interval; the "
        "pre-harvest interval for triadimefon on apple is generally 20 days."
    ),
    ("apple_cedar_apple_rust", "ECOLOGICAL"): (
        "1) Grow grass between orchard rows to improve the microclimate. 2) Protect and use antagonistic "
        "microorganisms such as Bacillus. 3) Avoid mass planting of junipers in ornamental green belts "
        "around the orchard. 4) Prune sensibly to increase the tree's tolerance of the disease."
    ),
    ("apple_cedar_apple_rust", "MONITORING"): (
        "1) After spring rain, check junipers for the amount of telial horns produced and predict the "
        "basidiospore release peak. 2) The monitoring window runs from tight cluster to 14 days after "
        "petal fall; survey marked trees for the percentage of orange-yellow lesions on the upper leaf "
        "surface. 3) Combined with spring rainfall forecasts, complete spraying 2-3 days before "
        "basidiospore release. 4) When juniper gall density is high and continuous spring rain is "
        "forecast, issue an early warning in advance."
    ),
    ("apple_cedar_apple_rust", "PHYSICAL"): (
        "1) In spring and autumn cut out all galls and telial horns from the junipers and burn them, "
        "especially before spring rain. 2) Before the apple trees leaf out, cut off the basidiospore "
        "dispersal route as far as possible. 3) Bag the fruit to protect it. 4) Do not plant susceptible "
        "apple varieties close to junipers."
    ),
    # ------------------------------------------------------------------
    # cherry_powdery_mildew -- powdery mildew
    # ------------------------------------------------------------------
    ("cherry_powdery_mildew", "AGRICULTURAL"): (
        "1) Choose resistant varieties (mid- and late-season sweet cherries are more susceptible, so pay "
        "attention to variety layout). 2) Prune sensibly, thinning out excessively dense and excessively "
        "vigorous shoots inside the canopy, to improve airflow and light and above all to lower the "
        "humidity of the inner-canopy microclimate. 3) Apply more phosphate and potash fertiliser and "
        "avoid excessive nitrogen to check excessive shoot growth. 4) In autumn and winter sweep up "
        "fallen leaves and remove diseased shoots during pruning to reduce overwintering inoculum. "
        "5) Grow grass in the orchard but mow it in time so that the sward does not become tall enough "
        "to shade and close the orchard."
    ),
    ("cherry_powdery_mildew", "CHEMICAL"): (
        "The key control period is from the end of full bloom to immediately after petal fall, when the "
        "first spray is applied to protect the fruit; if necessary spray once more after an interval of "
        "14-21 d, and spray again at once if lesions are found on inner-canopy or water shoots. Commonly "
        "used products in China (rotate by mode of action, FRAC group; the same group should not be used "
        "more than twice in a row within a year): triazoles -- difenoconazole, tebuconazole, hexaconazole, "
        "myclobutanil (FRAC group 3); strobilurins -- kresoxim-methyl, azoxystrobin, pyraclostrobin (FRAC "
        "group 11); SDHI fungicides -- isopyrazam, fluopyram; protectants -- 80% mancozeb, colloidal "
        "sulphur (sulphur products are liable to cause phytotoxicity when the temperature is above 32 °C "
        "and must not be mixed with mineral oil). Note: 1) Sulphur products and lime sulphur are used only "
        "in the dormant period and should be avoided during the growing season. 2) Strictly observe the "
        "pre-harvest interval (PHI): for example kresoxim-methyl has a PHI of 1 d and myclobutanil a PHI of "
        "0 d, while difenoconazole follows the label. 3) Do not use products with the same mode of action "
        "more than twice in succession, to delay resistance. 4) Direct the spray mainly into the inner "
        "canopy and at the new shoots."
    ),
    ("cherry_powdery_mildew", "ECOLOGICAL"): (
        "1) Keep beneficial weeds (ageratum, mint) in the orchard to improve the ecology. 2) Spray "
        "Bacillus subtilis (for example strain QST 713) or baking soda / potassium bicarbonate, which "
        "meets organic production requirements. 3) Avoid products highly toxic to bees and use them with "
        "care during bloom. 4) Protect insects such as hoverflies and thrips that feed on powdery mildew "
        "conidia."
    ),
    ("cherry_powdery_mildew", "MONITORING"): (
        "1) From petal fall survey inner-canopy shoot leaves and fruit every week and spray at once when "
        "lesions are first seen. 2) Predict the disease peak from the weather conditions, namely "
        "temperatures of 21-27 °C and little rainfall. 3) Monitor inner-canopy water shoots and "
        "excessively vigorous shoots in particular, as these are the early centres of inoculum. "
        "4) Two weeks before harvest re-check the fruit surface for disease so that affected fruit is "
        "not sent to market."
    ),
    ("cherry_powdery_mildew", "PHYSICAL"): (
        "1) In protected cultivation improve ventilation and air exchange, control the humidity inside "
        "the house and avoid hot, muggy, humid conditions. 2) Hand-pick the first diseased leaves and "
        "shoots and take them out of the orchard for deep burial. 3) In the dormant period spray 3-5 \u00b0B\u00e9 "
        "lime sulphur to eradicate overwintering inoculum. 4) Use sensible row spacing to "
        "ensure ventilation between canopies."
    ),
    # ------------------------------------------------------------------
    # corn_gray_leaf_spot -- Cercospora leaf spot
    # ------------------------------------------------------------------
    ("corn_gray_leaf_spot", "AGRICULTURAL"): (
        "1) Choose resistant varieties (the most economic and effective measure). 2) Rotate for 2-3 years "
        "with non-host crops such as soybean or peanut. 3) After the autumn harvest plough deeply to "
        "destroy the stubble and reduce surface residue (bringing stubble cover down to a low level can "
        "markedly reduce primary inoculum). 4) Use a sensible plant density to improve ventilation and "
        "lower humidity. 5) Fertilise in a balanced way and avoid excessive nitrogen."
    ),
    ("corn_gray_leaf_spot", "CHEMICAL"): (
        "Prevention comes first, and the critical preventive window runs from the large trumpet stage to "
        "tasselling and silking. Options are 25% azoxystrobin suspension concentrate at 1000-1500x, 18.7% "
        "propiconazole + azoxystrobin emulsifiable concentrate at 1000x, 25% pyraclostrobin emulsifiable "
        "concentrate at 1000x, or 25% difenoconazole emulsifiable concentrate at 8000-10000x; spray once "
        "every 7-10 days "
        "for 1-2 consecutive applications and rotate products with different modes of action."
    ),
    ("corn_gray_leaf_spot", "ECOLOGICAL"): (
        "1) Intercrop with legumes to improve field ventilation and reduce leaf wetness. 2) Apply "
        "biocontrol preparations such as Bacillus subtilis. 3) Fertilise in a balanced way and apply more "
        "organic manure to increase the plants' tolerance of the disease. 4) Reduce straw cover on the "
        "soil surface to lower primary inoculum."
    ),
    ("corn_gray_leaf_spot", "MONITORING"): (
        "1) From tasselling, survey the middle and lower leaves for disease at regular intervals. "
        "2) Start fungicide control when the percentage of diseased leaves reaches 15%-20%. 3) Predict "
        "epidemic risk from spells of overcast and rainy weather, heavy dew and the amount of straw "
        "returned to the field. 4) List continuous-cropping fields that were badly affected the previous "
        "year as priority monitoring targets."
    ),
    ("corn_gray_leaf_spot", "PHYSICAL"): (
        "1) Plough deeply to bury crop residue and reduce inoculum on the soil surface. 2) Use a sensible "
        "plant density and wide-narrow row planting to improve ventilation and light. 3) Improve drainage "
        "in low-lying land to lower field humidity."
    ),
    # ------------------------------------------------------------------
    # corn_common_rust -- common rust
    # ------------------------------------------------------------------
    ("corn_common_rust", "AGRICULTURAL"): (
        "1) Choose resistant hybrids. 2) Fertilise sensibly, applying more phosphate and potash fertiliser "
        "and avoiding excessive nitrogen, to strengthen plant resistance. 3) Use a sensible plant density "
        "to improve ventilation and light. 4) At the first sign of disease promptly remove the diseased "
        "leaves at the base and take them out of the field for disposal."
    ),
    ("corn_common_rust", "CHEMICAL"): (
        "Seize the critical window at the first sign of disease. Options are 25% triadimefon wettable "
        "powder at 1500-2000x, 25% propiconazole emulsifiable concentrate at 3000x, 12.5% diniconazole "
        "wettable powder at 4000-5000x, or tebuconazole, difenoconazole, pyraclostrobin, epoxiconazole and "
        "similar products; spray once every 7-10 days, with 1-2 consecutive applications depending on "
        "disease development, directing the spray at both surfaces of the middle and lower leaves. If it "
        "rains after spraying, respray in good time."
    ),
    ("corn_common_rust", "ECOLOGICAL"): (
        "1) Intercrop with legumes to improve field ventilation and lower leaf humidity. 2) Protect "
        "beneficial microorganisms and natural enemies in the field. 3) Fertilise in a balanced way to "
        "increase the plants' tolerance of the disease. 4) Combine with the mid- and late-season single "
        "spray for multiple benefits to control insects and disease together."
    ),
    ("corn_common_rust", "MONITORING"): (
        "1) From stem elongation, survey the middle and lower leaves at regular intervals for the "
        "percentage of diseased leaves. 2) Spray at once as soon as the percentage of diseased leaves "
        "reaches about 5% or the first uredinia appear. 3) Predict the epidemic from forecasts of "
        "inoculum moving north on the airstream from the south together with local rainfall and dew "
        "forecasts. 4) Link monitoring with that for southern rust, distinguishing the two rusts "
        "accurately before spraying the right product."
    ),
    ("corn_common_rust", "PHYSICAL"): (
        "1) Use a sensible plant density and wide-narrow row planting to improve ventilation and light. "
        "2) Improve field drainage to lower humidity. 3) Clear weed hosts in and around the field to "
        "reduce inoculum."
    ),
    # ------------------------------------------------------------------
    # corn_northern_leaf_blight -- northern leaf blight
    # ------------------------------------------------------------------
    ("corn_northern_leaf_blight", "AGRICULTURAL"): (
        "1) Choose resistant hybrids (the most economic and effective measure). 2) Rotate with non-host "
        "crops such as soybean or peanut. 3) After the autumn harvest plough deeply to destroy the "
        "stubble and bury crop residue in the soil so that it decomposes faster, reducing primary "
        "inoculum. 4) Use a sensible plant density and avoid excessive density. 5) Apply more organic "
        "manure and phosphate and potash fertiliser, and avoid excessive nitrogen, to strengthen plant "
        "resistance. 6) Drain low-lying land in good time."
    ),
    ("corn_northern_leaf_blight", "CHEMICAL"): (
        "The action threshold is around tasselling, when 70% of plants or 20% of leaves in the field are "
        "diseased. Options are 70% mancozeb wettable powder at 500x (protectant), 25% azoxystrobin "
        "suspension concentrate at 2000x (protectant), or systemic curative triazoles such as 30% "
        "pyraclostrobin + tebuconazole, difenoconazole and propiconazole; spray once every 7-10 days for "
        "1-2 consecutive applications and rotate products with different modes of action to delay "
        "resistance."
    ),
    ("corn_northern_leaf_blight", "ECOLOGICAL"): (
        "1) Intercrop or relay crop with crops such as soybean or peanut to improve the ventilation, "
        "light and microclimate of the field. 2) Apply biocontrol agents such as Trichoderma and Bacillus "
        "subtilis. 3) Fertilise in a balanced way and apply more bio-organic fertiliser to improve the "
        "rhizosphere microecology and increase the plants' tolerance of the disease. 4) Protect natural "
        "enemies and beneficial microbial communities in the field."
    ),
    ("corn_northern_leaf_blight", "MONITORING"): (
        "1) From stem elongation, survey the lower leaves at regular intervals from the bottom upwards "
        "and record the percentage of diseased leaves. 2) Start fungicide control when the percentage of "
        "diseased leaves reaches 20% (or 70% of plants are diseased). 3) Predict epidemic trends from "
        "spells of continuous rain, foggy and dewy weather and low-temperature forecasts. 4) In the main "
        "maize production areas carry out fixed-point surveys in systematic observation plots to guide "
        "well-timed control."
    ),
    ("corn_northern_leaf_blight", "PHYSICAL"): (
        "1) After the autumn harvest clear away crop residue completely and dispose of it centrally, "
        "ploughing deeply to bury it. 2) Use a sensible plant density and wide-narrow row planting to "
        "improve airflow and light in the stand and reduce leaf wetness. 3) Plastic film mulching can "
        "reduce the probability of primary infection."
    ),
    # ------------------------------------------------------------------
    # grape_black_rot -- black rot
    # ------------------------------------------------------------------
    ("grape_black_rot", "AGRICULTURAL"): (
        "1) In autumn and winter clear mummified berries, diseased leaves and diseased shoots out of the "
        "vineyard completely and burn or deep-bury them. 2) In spring plough the soil deeply to bury "
        "fallen mummies in the deeper layers and reduce ascospore release. 3) Strengthen summer pruning, "
        "thinning out excessively dense shoots and canes to improve airflow and light and help the "
        "clusters dry quickly. 4) Apply more organic manure and avoid excessive nitrogen."
    ),
    ("grape_black_rot", "CHEMICAL"): (
        "Before budbreak spray 3-5 °Bé lime sulphur or an equal-strength Bordeaux mixture to "
        "eradicate overwintering inoculum; during the growing season, from leaf expansion to the young "
        "fruit stage (before bloom, after bloom and fruit enlargement are the key timings), spray "
        "protectant fungicides such as mancozeb and chlorothalonil, or systemic curative fungicides such "
        "as difenoconazole, tebuconazole and propiconazole, once every 10-14 days for 3-4 consecutive "
        "applications; spray a protectant before rain and a curative product after rain, and rotate "
        "products with different modes of action."
    ),
    ("grape_black_rot", "ECOLOGICAL"): (
        "1) Grow grass in the vineyard to improve the microclimate and lower the humidity around the "
        "clusters. 2) Apply biocontrol agents such as Trichoderma and Bacillus to treat crop residue. "
        "3) Reduce the use of broad-spectrum fungicides to protect beneficial microorganisms on the "
        "leaves."
    ),
    ("grape_black_rot", "MONITORING"): (
        "1) From before bloom, survey leaves and clusters for disease at regular intervals. 2) The "
        "period from the pea-size stage to veraison is the key monitoring period: check once a week. "
        "3) Check disease development immediately after rain, patrolling the lower part of the trellis "
        "and poorly ventilated places in particular. 4) Monitor spore release dynamics to guide the "
        "timing of spraying."
    ),
    ("grape_black_rot", "PHYSICAL"): (
        "1) In autumn and winter, together with pruning, remove every mummified berry from the vines and "
        "cut out diseased shoots. 2) During the growing season remove the first diseased berries in good "
        "time and take them out of the vineyard. 3) Fruit bagging can block infection of the clusters. "
        "4) Avoid mechanical injury to the fruit during orchard operations."
    ),
    # ------------------------------------------------------------------
    # grape_black_measles -- esca (black measles)
    # ------------------------------------------------------------------
    ("grape_black_measles", "AGRICULTURAL"): (
        "1) Use certified disease-free nursery stock and check the cross-section of the trunk and limbs "
        "before planting. 2) Fertilise sensibly to build vine vigour, and avoid both waterlogging and "
        "excessive drought in the vineyard. 3) Avoid pruning during the bleeding period (the early spring "
        "period of sap flow) and in the rain, so that the pathogen has fewer chances to enter through "
        "wounds. 4) Dig out heavily diseased, unproductive vines in good time."
    ),
    ("grape_black_measles", "CHEMICAL"): (
        "There is no specific curative product for this disease, so prevention comes first: immediately "
        "after pruning paint the larger pruning and saw cuts with a wound sealant (containing "
        "thiophanate-methyl, myclobutanil or a boron-containing paint such as B-Lock) to block entry of "
        "the pathogen; overseas trials in which cuts were painted with Trichoderma preparations gave some "
        "protection. Applying large volumes of fungicide as a drench to vines that already show symptoms "
        "is not recommended."
    ),
    ("grape_black_measles", "ECOLOGICAL"): (
        "1) Apply more organic manure and microbial fertiliser to improve the rhizosphere microecology and "
        "increase the vines' tolerance of the disease. 2) Apply biocontrol agents such as Trichoderma to "
        "treat pruning wounds. 3) Grow grass in the vineyard to maintain a healthy rhizosphere "
        "environment and reduce root stress."
    ),
    ("grape_black_measles", "MONITORING"): (
        "1) In summer (the fruit development period) inspect leaves regularly for tiger-stripe necrotic "
        "symptoms. 2) After rain or after hot, dry weather, watch for vines with sudden wilting. 3) In old "
        "vineyards keep a disease record, marking the disease status of each vine. 4) Combine this with a "
        "survey of vine vigour to decide whether a diseased vine should be kept or removed."
    ),
    ("grape_black_measles", "PHYSICAL"): (
        "1) Practise double pruning, delaying the pruning date to reduce wound infection. 2) Paint wounds "
        "with a wound sealant immediately after pruning. 3) Cut out diseased branches and take them out "
        "of the vineyard for burning, avoiding mechanical damage. 4) Irrigate sensibly during dry periods "
        "and drain promptly in the rainy season, so that vine stress does not trigger sudden apoplexy."
    ),
    # ------------------------------------------------------------------
    # grape_leaf_blight -- grape leaf blight
    # ------------------------------------------------------------------
    ("grape_leaf_blight", "AGRICULTURAL"): (
        "1) After the autumn harvest, together with deep cultivation, sweep up fallen leaves completely "
        "and deep-bury or burn them to reduce overwintering inoculum. 2) Strengthen summer pruning, tying "
        "shoots promptly, pinching tips and thinning out laterals, to improve ventilation and light on "
        "the trellis and lower leaf humidity. 3) Apply more organic manure and phosphate and potash "
        "fertiliser and avoid excessive nitrogen to build vine vigour. 4) Pay attention to drainage in "
        "low-lying vineyards."
    ),
    ("grape_leaf_blight", "CHEMICAL"): (
        "At the first sign of disease, spray together with the control of grape anthracnose and ripe rot; "
        "options are 1:0.7:200 Bordeaux mixture, 70% mancozeb wettable powder at 500-600x, 75% "
        "chlorothalonil at 600x, or systemic triazoles such as difenoconazole and tebuconazole; spray "
        "once every 10-15 days for 2-3 consecutive applications, directing the spray at both surfaces of "
        "the lower leaves. Take care to rotate products."
    ),
    ("grape_leaf_blight", "ECOLOGICAL"): (
        "1) Grow grass between the rows to improve the vineyard microclimate and shorten leaf wetness "
        "duration. 2) Apply more bio-organic fertiliser to increase the diversity of beneficial "
        "microorganisms in the rhizosphere and on the leaves. 3) Protect and use phyllosphere "
        "antagonists such as Trichoderma."
    ),
    ("grape_leaf_blight", "MONITORING"): (
        "1) At the first sign of disease (usually around fruit enlargement) begin surveying the lower "
        "leaves at regular intervals for the percentage of diseased leaves. 2) Combined with rainfall "
        "forecasts, spray a protectant in good time before rain. 3) Start field-wide control when the "
        "percentage of diseased leaves rises markedly."
    ),
    ("grape_leaf_blight", "PHYSICAL"): (
        "1) In late autumn and early winter sweep up fallen leaves by hand and dispose of them centrally. "
        "2) During the growing season remove the first diseased leaves on the lower part of the vine in "
        "good time. 3) Use a sensible trellis system and shoot tying so that foliage does not become "
        "excessively dense."
    ),
    # ------------------------------------------------------------------
    # citrus_greening -- citrus huanglongbing (HLB)
    # ------------------------------------------------------------------
    ("citrus_greening", "AGRICULTURAL"): (
        "The core strategy is the three-part combination of removing diseased trees, planting disease-free "
        "nursery stock and controlling the psyllid vector: 1) Enforce strict quarantine, prohibiting the "
        "movement of citrus nursery stock and scion wood out of affected areas, and operate a healthy "
        "nursery stock certification scheme. 2) Establish disease-free nurseries (insect-proof screenhouse "
        "isolation and virus-free mother trees) and plant tested disease-free container-grown stock. "
        "3) In new orchards plant the same variety of the same tree age in contiguous blocks, avoiding "
        "mixed plantings of citrus with different maturity periods, which gives the psyllid food because "
        "the flushes are not synchronous. 4) Strengthen water and nutrient management, apply more organic "
        "manure and supply nutrients evenly so that flushes emerge uniformly and harden off, promoting "
        "uniform and timely hardening of new flushes. 5) For confirmed diseased trees, spray first to kill "
        "the psyllids and then dig the tree out at once, leaving a stump no higher than 10 cm; paint the "
        "cut surface with herbicide, kerosene, pitch or diesel and cover it with black film so that new "
        "shoots cannot emerge and attract psyllids, and burn or safely dispose of the dug-out trees "
        "centrally."
    ),
    ("citrus_greening", "CHEMICAL"): (
        "The target is the Asian citrus psyllid rather than the pathogen itself. Key timings: spray "
        "uniformly before the spring flush emerges and when each flush (spring, summer and autumn flush) "
        "has grown to 0.5-5 cm, and spray 1-2 times in the winter orchard clean-up to reduce overwintering "
        "insect sources. Products recommended in the 2025 programme of the National Agricultural "
        "Technology Extension and Service Centre (rotate different modes of action): thiamethoxam, "
        "imidacloprid, bifenthrin, flupyradifurone, abamectin + spirotetramat, spirotetramat + "
        "thiamethoxam and beta-cypermethrin + pyriproxyfen. Carry out joint coordinated control under the "
        "five unifications -- unified timing, unified products, unified application, unified inspection "
        "and unified follow-up treatment -- and promote aerial application with plant protection drones. "
        "Trunk injection of tetracycline or oxytetracycline hydrochloride can relieve symptoms temporarily "
        "but cannot eradicate the disease, and is not used as a routine measure; every spray must cover the "
        "inner canopy and nearby rutaceous plants such as orange jasmine and wampee."
    ),
    ("citrus_greening", "ECOLOGICAL"): (
        "1) Grow grass between orchard rows (such as ageratum or white clover) to improve the microclimate "
        "and protect psyllid parasitic wasps (such as the encyrtid wasps Tamarixia radiata and Aphidencyrtus "
        "spp.) and predatory natural enemies. 2) Avoid frequent use of broad-spectrum insecticides, so as "
        "to protect natural enemy populations. 3) Apply entomopathogenic fungi such as Lecanicillium "
        "lecanii and Beauveria bassiana to control psyllid nymphs. 4) Do not plant rutaceous plants that "
        "serve as bridging hosts for the psyllid, such as wampee and orange jasmine, around the orchard."
    ),
    ("citrus_greening", "MONITORING"): (
        "1) Follow GB/T 35333-2017, the specification for monitoring citrus huanglongbing, and GB/T "
        "35334-2017, the specification for monitoring the citrus psyllid. 2) Carry out 2-3 focused surveys "
        "when each flush hardens off, especially from the hardening of the autumn flush to fruit colour "
        "break. 3) In affected areas select representative plots in each county and set up 3 fixed "
        "monitoring points for fixed-point surveys; in frontier areas focus on monitoring the northern "
        "limit of psyllid distribution and test the psyllid carrying rate. 4) Test suspect trees for "
        "pathogen DNA in the leaf phloem by PCR or real-time quantitative PCR. 5) For psyllid surveys use "
        "five-point sampling, 5 trees per point and 10 leaves per tree, counting adults and nymphs."
    ),
    ("citrus_greening", "PHYSICAL"): (
        "1) Raise seedlings in 40-60 mesh insect-proof screenhouses to block psyllid contact with the "
        "nursery stock. 2) Whitewash the trunks to reduce psyllid egg-laying sites. 3) Hang yellow sticky "
        "traps at the top of the canopy to trap and kill adult psyllids and to monitor population density. "
        "4) Site new orchards at least 5 km away from old diseased orchards. 5) Before replanting an old "
        "orchard, spray the whole orchard and only then cut the trees, 1-3 d beforehand, to prevent "
        "psyllid dispersal."
    ),
    # ------------------------------------------------------------------
    # peach_bacterial_spot -- bacterial spot
    # ------------------------------------------------------------------
    ("peach_bacterial_spot", "AGRICULTURAL"): (
        "1) Establish the orchard on a sunny, well-ventilated, well-drained site; do not plant peaches "
        "together with stone fruits such as plum, apricot or cherry, keeping a separation of more than "
        "5 km. 2) Choose resistant varieties; early-maturing varieties are less affected than "
        "late-maturing ones. 3) Apply more rotted organic manure and microbial fertiliser, avoid excessive "
        "nitrogen and prevent the soil from becoming acidified and compacted. 4) Prune sensibly so that "
        "the canopy is well ventilated and lit. 5) In winter, together with pruning, cut out diseased "
        "branches completely and sweep up fallen leaves, burning them centrally to reduce overwintering "
        "inoculum. 6) Control pests such as the green peach aphid and peach leaf miner to reduce wounds "
        "and transmission vectors. 7) Paint pruning wounds with a wound-healing agent for protection."
    ),
    ("peach_bacterial_spot", "CHEMICAL"): (
        "1) At budbreak (from bud swelling to pink bud): spray 5 °Bé lime sulphur, or 45% lime "
        "sulphur crystals at 8x, or 3% zhongshengmycin wettable powder at 600-700x, or 20% thiosen copper "
        "suspension concentrate at 600x, to eradicate overwintering inoculum. 2) From 80% petal fall (the "
        "end of pink bud to the young fruit stage): spray 72% agricultural streptomycin wettable powder at "
        "3000x (note: agricultural streptomycin sulphate is no longer registered for use on fruit trees "
        "and vegetables in China; use zhongshengmycin or kasugamycin instead), 1.5% benziothiazolinone "
        "suspension concentrate at 800x, 20% bismerthiazol wettable powder at 600x, 50% chloroisobromine "
        "cyanuric acid wettable powder at 2000-2500x, or copper products such as 20% zinc thiazole and "
        "33.5% oxine-copper. Spray once every 7-10 d for 3-4 consecutive applications. 3) Take care over "
        "the incompatibility of copper products when tank-mixed with other pesticides, and avoid spraying "
        "copper under hot sun, which causes phytotoxicity; rotate products with different modes of action "
        "to delay resistance. Observe the pre-harvest interval before harvesting the fruit."
    ),
    ("peach_bacterial_spot", "ECOLOGICAL"): (
        "1) Grow grass between orchard rows (white clover, ryegrass) to improve the microclimate and "
        "shorten leaf wetness duration. 2) Apply beneficial microorganisms such as Bacillus subtilis and "
        "Pseudomonas as a root drench or spray, to compete for ecological niches. 3) Use drip irrigation "
        "instead of flood irrigation to reduce spread by rain splash. 4) Protect natural enemies such as "
        "ladybirds, lacewings and parasitic wasps to control aphids."
    ),
    ("peach_bacterial_spot", "MONITORING"): (
        "1) From leaf expansion begin fixed-point systematic surveys, checking once every 5 d, and start "
        "fungicide control when the percentage of diseased leaves reaches 10%. 2) Inspect the orchard "
        "promptly after rain and after storms, checking new shoots and young fruit in particular. 3) At "
        "the two disease peaks in spring and autumn, predict infection peaks from weather forecasts "
        "(temperature, humidity, rainfall). 4) Watch for the timing of spring canker lesions to guide the "
        "first spray."
    ),
    ("peach_bacterial_spot", "PHYSICAL"): (
        "1) In winter clean up the orchard, cutting out diseased branches and scraping off cankers on old "
        "bark, and burn the material centrally. 2) During the growing season hand-pick diseased leaves and "
        "fruit and take them out of the orchard for disposal. 3) Bag the fruit to block infection and to "
        "reduce sunscald and mechanical injury. 4) Drain promptly in the rainy season so that the canopy "
        "is not wet for long periods."
    ),
    # ------------------------------------------------------------------
    # pepper_bacterial_spot -- bacterial spot
    # ------------------------------------------------------------------
    ("pepper_bacterial_spot", "AGRICULTURAL"): (
        "1) Choose resistant varieties and disease-free seed. 2) Seed treatment: soak the seed in hot "
        "water at 55 °C for 30 min, or soak it in 1% hydrochloric acid for 5-10 min and then wash it, or "
        "soak it in 200 mg/L agricultural streptomycin sulphate for 2 h. 3) Rotate with non-solanaceous "
        "crops (legumes, crucifers) for 2-3 years. 4) Grow on raised beds, irrigate through furrows or by "
        "drip, and avoid flood irrigation and rain splash. 5) Remove crop residue promptly and deep-bury "
        "or burn it centrally after harvest. 6) Carry out operations such as pruning and sucker removal "
        "after the dew on the leaves has dried."
    ),
    ("pepper_bacterial_spot", "CHEMICAL"): (
        "1) At the first sign of disease spray copper products: 77% copper hydroxide wettable powder at "
        "500-800x and 20% zinc thiazole suspension concentrate at 500x. 2) Antibiotics: zhongshengmycin, "
        "kasugamycin, agricultural streptomycin sulphate (note that streptomycin is now restricted). "
        "3) Protectants: mancozeb, chlorothalonil. 4) Spray at once after rain or at the first lesions, "
        "once every 7-10 days for 2-3 consecutive applications. 5) Rotate copper products with antibiotics "
        "to avoid resistance. 6) Note that copper products may cause phytotoxicity at the pepper seedling "
        "stage, so a lower concentration is advisable."
    ),
    ("pepper_bacterial_spot", "ECOLOGICAL"): (
        "1) Apply biocontrol agents such as Bacillus subtilis and Pseudomonas. 2) Use drip irrigation "
        "instead of flood irrigation to reduce spread by rain splash. 3) In protected cultivation improve "
        "ventilation and reduce humidity to shorten leaf wetness duration. 4) Apply more rotted organic "
        "manure and microbial fertiliser to improve the rhizosphere microecology."
    ),
    ("pepper_bacterial_spot", "MONITORING"): (
        "1) From transplanting to the fruiting period survey the lower leaves at regular intervals for the "
        "percentage of diseased leaves and spray at once when lesions are first seen. 2) After rain "
        "(especially after storms) check the disease promptly and respray. 3) Monitor seed-production and "
        "seedling-raising fields as a priority. 4) Combined with forecasts of hot, humid weather, spray "
        "protectively before rain."
    ),
    ("pepper_bacterial_spot", "PHYSICAL"): (
        "1) Treat seed with hot water (55 °C for 30 min) or hydrochloric acid. 2) In protected "
        "cultivation ventilate to remove moisture and avoid long periods of leaf wetness. 3) Remove lower "
        "diseased leaves and fruit promptly and take them out of the field for destruction. 4) During the "
        "fallow period close the house for soil solarisation (35-38 °C for 3-5 days)."
    ),
    # ------------------------------------------------------------------
    # potato_early_blight -- early blight
    # ------------------------------------------------------------------
    ("potato_early_blight", "AGRICULTURAL"): (
        "1) Choose resistant or tolerant varieties. 2) Use healthy virus-free seed tubers. 3) Rotate with "
        "non-solanaceous crops for 2-3 years. 4) Apply more organic manure and phosphate and potash "
        "fertiliser, and spray foliar fertiliser such as monopotassium phosphate during the growing season "
        "to prevent premature ageing of the plants. 5) Irrigate sensibly and avoid prolonged high humidity "
        "in the field."
    ),
    ("potato_early_blight", "CHEMICAL"): (
        "At the first sign of disease (when lesions are first seen) spray protectant fungicides such as "
        "propineb or mancozeb 1-2 times in good time; if the disease is more severe, switch to curative "
        "fungicides such as propiconazole, azoxystrobin, boscalid, difenoconazole or a "
        "pyraclostrobin + metiram mixture, once every 7-10 days for 2-3 consecutive applications, "
        "directing the spray at both surfaces of the lower leaves."
    ),
    ("potato_early_blight", "ECOLOGICAL"): (
        "1) Apply biocontrol agents such as Trichoderma and Bacillus. 2) Rotate with graminaceous and "
        "leguminous crops to reduce the build-up of inoculum. 3) Fertilise in a balanced way to "
        "strengthen plant resistance."
    ),
    ("potato_early_blight", "MONITORING"): (
        "1) From budding and flowering begin surveying the lower, older leaves for disease at regular "
        "intervals. 2) Start fungicide control when the percentage of diseased leaves reaches about 5%. "
        "3) Combined with rainfall and temperature forecasts, give priority warnings during alternating "
        "sunny and rainy spells."
    ),
    ("potato_early_blight", "PHYSICAL"): (
        "1) Sort the seed tubers before planting and discard diseased ones. 2) Remove the first diseased "
        "leaves in good time. 3) After harvest clear crop residue out of the field completely and plough "
        "deeply."
    ),
    # ------------------------------------------------------------------
    # potato_late_blight -- late blight
    # ------------------------------------------------------------------
    ("potato_late_blight", "AGRICULTURAL"): (
        "1) Choose resistant varieties. 2) Disease-free seed tubers (virus-free seed tubers) must be "
        "used; discard diseased and rotten tubers before planting. 3) Use a sensible plant density and "
        "hill up in good time to block infection of the tubers by sporangia washed down by rain. "
        "4) Avoid planting next to tomato. 5) Remove primary infected plants from the field in good time."
    ),
    ("potato_late_blight", "CHEMICAL"): (
        "Following the principle of prevention first and integrated control: before disease appears spray "
        "protectant fungicides such as mancozeb, mandipropamid, cyazofamid, fluazinam or copper hydroxide "
        "for prevention; once a primary infected plant is found or the epidemic period begins, spray "
        "systemic curative fungicides such as dimethomorph, fluopicolide + propamocarb (Infinito), "
        "cymoxanil, oxathiapiprolin or fosetyl-aluminium and their mixtures at once, once every 5-7 days "
        "for 2-3 consecutive applications. [IMPORTANT] National monitoring in 2024 showed that potato late "
        "blight in China has developed moderate to high levels of resistance to metalaxyl, with the "
        "frequency of highly resistant strains above 80%; metalaxyl and its mixtures should be "
        "discontinued in all main production areas, and products with different modes of action should be "
        "alternated to delay resistance."
    ),
    ("potato_late_blight", "ECOLOGICAL"): (
        "1) Apply biological preparations such as Bacillus subtilis for prevention. 2) Fertilise sensibly "
        "and avoid excessive nitrogen, which makes the plants soft and succulent. 3) Use drip irrigation "
        "to lower field humidity and leaf wetness."
    ),
    ("potato_late_blight", "MONITORING"): (
        "1) After budding assign staff to patrol at set times and report primary infected plants to the "
        "local plant protection department immediately. 2) Combined with weather forecasts, spray for "
        "protection at once before spells of continuous rain and cool, humid weather. 3) Use spore traps "
        "and forecasting models to guide control. 4) In heavily affected areas begin preventive spraying "
        "as soon as the plants emerge."
    ),
    ("potato_late_blight", "PHYSICAL"): (
        "1) Use strictly virus-free, disease-free seed tubers. 2) Rogue out primary infected plants at "
        "once, take them out of the field for deep burial and spray the surrounding plants to seal off the "
        "focus. 3) Destroy the haulm 7-10 days before harvest (chemical or mechanical haulm destruction) "
        "to reduce infection of the tubers by sporangia washed off the plants. 4) After harvest dry the "
        "tubers before storing and discard diseased ones."
    ),
    # ------------------------------------------------------------------
    # pumpkin_powdery_mildew -- powdery mildew
    # ------------------------------------------------------------------
    ("pumpkin_powdery_mildew", "AGRICULTURAL"): (
        "1) Choose resistant varieties (resistance differs markedly between pumpkin types, which matters "
        "especially in seed-production fields). 2) Use a sensible plant density and prune, press the vines "
        "and remove old leaves in good time to improve ventilation and light. 3) Avoid excessive nitrogen; "
        "apply more phosphate and potash fertiliser and rotted organic manure to prevent excessive growth. "
        "4) Rotate with non-cucurbit crops for more than 2 years. 5) After harvest clear crop residue "
        "completely and deep-bury or burn it centrally."
    ),
    ("pumpkin_powdery_mildew", "CHEMICAL"): (
        "Spray in good time at the first sign of disease, once every 7-10 days for 2-3 consecutive "
        "applications, directing the spray at both surfaces of the middle and lower leaves. Options are "
        "25% ethirimol suspension concentrate at 1500-2500x; 30% kresoxim-methyl suspension concentrate at "
        "1500-2500x; 30% triflumizole wettable powder at 1500-2000x; 430 g/L tebuconazole suspension "
        "concentrate; 10% difenoconazole water-dispersible granules at 1500-2500x; 25% triadimefon "
        "wettable powder at 2000x. Take care to rotate triazoles, strobilurins (kresoxim-methyl / "
        "pyraclostrobin) and pyrimidines (ethirimol) to delay resistance. In protected cultivation, "
        "chlorothalonil smoke generators can be used in the evening with the house closed."
    ),
    ("pumpkin_powdery_mildew", "ECOLOGICAL"): (
        "1) Before disease appears or at the first sign, spray biological preparations such as Bacillus "
        "subtilis wettable powder (1000 x 10^8 spores/g) at 500x. 2) Keep humidity at a suitable level in "
        "protected cultivation and avoid excessively long periods of dew. 3) Grow grass between the rows or "
        "use a cover to improve the field microclimate. 4) Protect natural enemies such as ladybirds and "
        "lacewings."
    ),
    ("pumpkin_powdery_mildew", "MONITORING"): (
        "1) From transplanting to the vine-running stage survey the lower leaves at regular intervals and "
        "start fungicide control as soon as lesions are first seen. 2) Combined with weather forecasts, "
        "take preventive action before spells of continuous hot sunshine, large day-night temperature "
        "differences and night dew. 3) Where possible use a spore trap to monitor the amount of airborne "
        "conidia. 4) In seed-production fields the period around pollination is the key monitoring window."
    ),
    ("pumpkin_powdery_mildew", "PHYSICAL"): (
        "1) In protected cultivation improve ventilation and air exchange, keeping the daytime temperature "
        "below 28 °C and preventing the night temperature from falling so low that dew forms. 2) Soil "
        "solarisation: close the house and raise the temperature to 35-38 °C for 2 hours, which "
        "suppresses powdery mildew. 3) Remove diseased and old lower leaves in good time and take them out "
        "of the field for disposal."
    ),
    # ------------------------------------------------------------------
    # strawberry_leaf_scorch -- leaf scorch
    # ------------------------------------------------------------------
    ("strawberry_leaf_scorch", "AGRICULTURAL"): (
        "1) Choose resistant varieties (resistance to leaf scorch differs markedly between strawberry "
        "varieties). 2) Plant disease-free, strong runners and avoid introducing planting material from "
        "affected areas. 3) Rotate with rice or non-rosaceous crops for 2-3 years and avoid continuous "
        "cropping. 4) Remove old and diseased leaves in good time and take them out of the field for "
        "central destruction. 5) Use a sensible plant density to improve ventilation and light and reduce "
        "leaf wetness."
    ),
    ("strawberry_leaf_scorch", "CHEMICAL"): (
        "The period from budding to flowering is the key period for fungicide protection. At the first "
        "sign of disease spray protectant fungicides such as mancozeb or chlorothalonil, or systemic "
        "curative fungicides such as difenoconazole, thiophanate-methyl (Topsin M) or azoxystrobin, once "
        "every 7-10 days for 2-3 consecutive applications. Coordinate the programme with products used "
        "against grey mould and powdery mildew and rotate them to delay resistance. Observe the "
        "pre-harvest interval before harvest."
    ),
    ("strawberry_leaf_scorch", "ECOLOGICAL"): (
        "1) Spray biocontrol agents such as Bacillus subtilis and Trichoderma for prevention. 2) Use drip "
        "irrigation instead of flood irrigation to reduce splash on the leaves and soil surface. 3) "
        "Ventilate protected cultivation sensibly to lower the relative humidity of the air. 4) Grow grass "
        "between the rows to improve the microclimate."
    ),
    ("strawberry_leaf_scorch", "MONITORING"): (
        "1) From planting to flowering survey the lower leaves at regular intervals for the percentage of "
        "diseased leaves, paying particular attention to identifying dark purple irregular lesions and the "
        "small black dots on the upper leaf surface (acervuli). 2) Check disease spread promptly after "
        "rain. 3) Start fungicide control when the percentage of diseased leaves reaches about 5% or "
        "lesions are first seen. 4) Take care to distinguish this from strawberry anthracnose (sunken "
        "cankers and pink spore masses), grey mould (grey-brown mould and soft rot of the fruit) and "
        "powdery mildew (white powdery mould)."
    ),
    ("strawberry_leaf_scorch", "PHYSICAL"): (
        "1) Before planting clear crop residue from the field and solarise the soil or use high-temperature "
        "solarisation in protected houses. 2) Hand-pick diseased and old leaves. 3) Use plastic film "
        "mulching to reduce spread by rain splash. 4) Thin the leaves of propagation beds at regular "
        "intervals."
    ),
    # ------------------------------------------------------------------
    # tomato_bacterial_spot -- bacterial spot
    # ------------------------------------------------------------------
    ("tomato_bacterial_spot", "AGRICULTURAL"): (
        "1) Use disease-free seed and treat the seed: hot water at 52 °C for 30 minutes, or soaking in "
        "1% hydrochloric acid for 5 minutes, or soaking in 0.6% sodium hypochlorite. 2) Rotate with "
        "non-solanaceous crops for 2-3 years. 3) Use raised beds with plastic mulch and drip irrigation or "
        "subsurface drip under mulch, avoiding flood irrigation and rain splash. 4) Prune and remove "
        "suckers in good time and avoid working the crop when the plants are wet with dew. 5) Remove crop "
        "residue promptly."
    ),
    ("tomato_bacterial_spot", "CHEMICAL"): (
        "Spray at the first sign of disease, once every 7-10 days for 2-3 consecutive applications. "
        "Options are kasugamycin wettable powder (for example 2% kasugamycin aqueous solution at 500x, "
        "with a 15-day pre-harvest interval), zhongshengmycin (3% zhongshengmycin aqueous solution at "
        "500x), zinc thiazole (20% zinc thiazole suspension concentrate at 500x), copper hydroxide (77% "
        "Kocide wettable powder at 800x), cuprous oxide and streptomycin sulphate (now restricted). Note "
        "that copper products are liable to cause phytotoxicity under high temperature and strong light "
        "and should not be tank-mixed with other pesticides at will; rotate antibiotics (kasugamycin, "
        "zhongshengmycin) with copper products to delay resistance. Strictly observe the pre-harvest "
        "interval before harvest."
    ),
    ("tomato_bacterial_spot", "ECOLOGICAL"): (
        "1) In protected cultivation improve ventilation and moisture removal to shorten leaf wetness "
        "duration. 2) Apply beneficial microorganisms such as Bacillus subtilis and Pseudomonas "
        "fluorescens. 3) Use drip irrigation instead of flood irrigation. 4) Use a sensible plant density "
        "and prune promptly to improve ventilation."
    ),
    ("tomato_bacterial_spot", "MONITORING"): (
        "1) Survey the leaves at regular intervals after transplanting and spray as soon as dark spots are "
        "first seen. 2) Spray preventively before spells of cool, rainy weather (16-24 °C with "
        "continuous rain). 3) Check the disease promptly after rain. 4) Take care to distinguish it from "
        "bacterial spot and, where necessary, send samples for laboratory testing."
    ),
    ("tomato_bacterial_spot", "PHYSICAL"): (
        "1) Treat seed with hot water or disinfect with hydrochloric acid or sodium hypochlorite. 2) Use "
        "plastic film mulching to block rain splash. 3) Remove diseased leaves promptly and take them out "
        "of the field. 4) Avoid carrying out operations such as pruning and sucker removal while the "
        "plants are covered in dew."
    ),
    # ------------------------------------------------------------------
    # tomato_early_blight -- early blight
    # ------------------------------------------------------------------
    ("tomato_early_blight", "AGRICULTURAL"): (
        "1) Choose resistant varieties and use disease-free seed. 2) Seed treatment: hot water at 52 °C "
        "for 30 minutes, or dress the seed with 2.5% fludioxonil suspension seed coating. 3) Rotate with "
        "non-solanaceous crops for 2-3 years, clearing residue of the previous crop and ploughing deeply. "
        "4) Apply plenty of rotted organic manure and more phosphate and potash fertiliser, and avoid "
        "excessive nitrogen. 5) Use a sensible plant density, prune and remove suckers in good time and "
        "remove old and diseased lower leaves to improve ventilation and light. 6) Use raised beds with "
        "plastic mulch and drip irrigation or subsurface drip under mulch, avoiding flood irrigation and "
        "prolonged leaf wetness."
    ),
    ("tomato_early_blight", "CHEMICAL"): (
        "Spray at once at the first sign of disease (when lesions are first seen or about 5% of leaves are "
        "diseased), once every 7-10 days for 3-4 consecutive applications. Options are 80% mancozeb "
        "wettable powder at 500-600x (registered rate 130-210 g/mu, pre-harvest interval 15 days), 75% "
        "chlorothalonil wettable powder at 500-600x (pre-harvest interval 7 days), 25% azoxystrobin "
        "suspension concentrate at 1000-1500x (pre-harvest interval 5 days), 10% difenoconazole "
        "water-dispersible granules at 1000-1500x (pre-harvest interval 7 days) and 70% propineb wettable "
        "powder at 500x. Take care to rotate protectants (mancozeb, chlorothalonil) with systemic curative "
        "fungicides (azoxystrobin, difenoconazole), using no more than 2 applications of the same mode of "
        "action per growing season to delay resistance; when spraying, pay particular attention to the "
        "lower leaves, the branch forks of the stem and the calyx end of the fruit."
    ),
    ("tomato_early_blight", "ECOLOGICAL"): (
        "1) In protected cultivation close the house in the morning and raise the temperature to 30-32 °C "
        "before ventilating to reduce humidity, keeping leaf wetness duration below 4 hours. 2) Apply "
        "biological preparations such as Bacillus subtilis, Trichoderma and Trichoderma harzianum for "
        "prevention. 3) Grow grass between the rows or cover with straw to improve the rhizosphere "
        "microecology. 4) Rotate with non-host crops and fertilise in a balanced way to raise strong "
        "seedlings."
    ),
    ("tomato_early_blight", "MONITORING"): (
        "1) From transplanting survey the lower, older leaves at regular intervals and start control as "
        "soon as lesions are first seen. 2) Combined with weather forecasts, respray in good time after "
        "rain or when humidity stays above 80% for more than 24 hours. 3) Where possible use a spore trap "
        "to monitor the amount of airborne conidia. 4) Treat the area 3-5 m around a primary infected "
        "plant as a priority protection zone."
    ),
    ("tomato_early_blight", "PHYSICAL"): (
        "1) Treat the seed with hot water (52 °C for 30 minutes) to kill seed-borne pathogens. 2) Before "
        "transplanting, close the greenhouse or house and use high-temperature solarisation (closing until "
        "36-38 °C and holding for 2 hours). 3) Remove diseased lower leaves and fruit promptly and take "
        "them out of the field for deep burial. 4) Use plastic film mulching to block splash dispersal of "
        "the pathogen from the soil."
    ),
    # ------------------------------------------------------------------
    # tomato_late_blight -- late blight
    # ------------------------------------------------------------------
    ("tomato_late_blight", "AGRICULTURAL"): (
        "1) Choose resistant varieties. 2) Avoid planting next to or in rotation with potato, and keep "
        "away from potato seed-production fields. 3) Use raised beds with plastic mulch and drip irrigation "
        "or subsurface drip under mulch to prevent flood irrigation. 4) Use a sensible plant density and "
        "prune and stake in good time; in protected cultivation improve ventilation, control the "
        "temperature by day and avoid dew at night. 5) Remove primary infected plants at once and take "
        "them out of the field for deep burial."
    ),
    ("tomato_late_blight", "CHEMICAL"): (
        "This is a devastating epidemic disease, so spray at once before disease appears or when the first "
        "primary infected plant is seen, once every 5-7 days for 2-3 consecutive applications, directing "
        "the spray at the area around the primary infected plant in particular. Options are 68% "
        "metalaxyl-M + mancozeb water-dispersible granules at 600-800x (pre-harvest interval 7 days), 72% "
        "cymoxanil + mancozeb wettable powder at 600-800x (pre-harvest interval 14 days), 50% dimethomorph "
        "wettable powder at 1500-2000x (pre-harvest interval 7 days), 25% azoxystrobin suspension "
        "concentrate at 1500x + 72.2% propamocarb aqueous solution at 800x (a mixture of a strobilurin "
        "with an amide/carbamate), 687.5 g/L fluopicolide + propamocarb suspension concentrate at 600-800x "
        "and 50% fluazinam suspension concentrate at 2000x. Products must be rotated: CAA and "
        "phenylamide fungicides such as dimethomorph, cymoxanil and metalaxyl should be used no more than "
        "2-3 times per growing season, alternating with products of different modes of action such as "
        "azoxystrobin, chlorothalonil and mancozeb, to prevent the late blight pathogen from developing "
        "resistance (paying particular attention to the known metalaxyl-resistant strains)."
    ),
    ("tomato_late_blight", "ECOLOGICAL"): (
        "1) In protected cultivation manage temperature and humidity as follows: close the house in the "
        "morning and raise the temperature to 28-32 °C before ventilating, close the house early in the "
        "afternoon and keep the night temperature at 10-13 °C, shortening leaf wetness duration as far "
        "as possible. 2) Apply beneficial microorganisms such as Pseudomonas and Trichoderma for "
        "prevention. 3) Use drip irrigation instead of flood irrigation to avoid rain splash."
    ),
    ("tomato_late_blight", "MONITORING"): (
        "1) Patrol daily during the growing season; if a primary infected plant is found, report it at "
        "once and spray the whole field. 2) When the forecast indicates 3 consecutive days of overcast "
        "rain, heavy fog morning and evening and temperatures of 15-22 °C, spray protectively at once. "
        "3) Where possible use a spore trap to monitor the amount of airborne sporangia. 4) Refer to late "
        "blight forecasting models (such as BLITECAST) to guide the timing of spraying."
    ),
    ("tomato_late_blight", "PHYSICAL"): (
        "1) Before transplanting, close the greenhouse or house and use high-temperature solarisation for "
        "disinfection. 2) Remove primary infected plants at once and sprinkle quicklime in the planting "
        "hole. 3) Avoid leaf wetness and promote the use of plastic film mulching. 4) Remove diseased "
        "leaves and fruit promptly and take them out of the field."
    ),
    # ------------------------------------------------------------------
    # tomato_leaf_mold -- leaf mould
    # ------------------------------------------------------------------
    ("tomato_leaf_mold", "AGRICULTURAL"): (
        "1) Choose resistant varieties carrying Cf resistance genes and rotate varieties periodically to "
        "keep up with changes in physiological races. 2) Seed treatment: hot water at 52 °C for 30 "
        "minutes, or dress the seed with fludioxonil or carbendazim. 3) Rotate with non-solanaceous crops "
        "for 2-3 years. 4) Before transplanting, close the greenhouse or house for high-temperature "
        "solarisation (30-35 °C for 3-4 hours, which suppresses mycelial growth). 5) Improve ventilation "
        "and moisture removal in the greenhouse, avoid high temperature and high humidity by day and "
        "ventilate promptly after watering. 6) Remove diseased and old lower leaves in good time."
    ),
    ("tomato_leaf_mold", "CHEMICAL"): (
        "Spray in good time at the first sign of disease, directing the spray at the underside of the "
        "leaves, once every 7-10 days for 2-3 consecutive applications. Options are 10% difenoconazole "
        "water-dispersible granules at 1000-1500x (pre-harvest interval 7 days), 25% azoxystrobin "
        "suspension concentrate at 1000-1500x (pre-harvest interval 5 days), 42.4% fluopyram + "
        "trifloxystrobin suspension concentrate at 3000x, 50% iprodione wettable powder at 1000x "
        "(pre-harvest interval 10 days) and 70% mancozeb wettable powder at 500x. In protected cultivation "
        "45% chlorothalonil smoke generators may be used in the evening at 200-250 g/mu, or 7% "
        "leaf-mould dust applied as a dust. Take care to rotate triazoles, strobilurins and "
        "dicarboximide fungicides, avoiding long-term use of a single product, which leads to resistance."
    ),
    ("tomato_leaf_mold", "ECOLOGICAL"): (
        "1) In protected cultivation use alternating temperature management: close the house in the "
        "morning and raise the temperature to 30 °C before ventilating to remove moisture, keep the "
        "afternoon at 20-25 °C with relative humidity below 70%, and avoid dew at night. 2) Apply "
        "biological preparations such as Bacillus subtilis and Trichoderma for prevention. 3) Use drip "
        "irrigation instead of flood irrigation through subsurface drip under mulch. 4) Use a sensible "
        "plant density and prune and remove suckers in good time to improve ventilation."
    ),
    ("tomato_leaf_mold", "MONITORING"): (
        "1) After transplanting survey the underside of the middle and lower leaves at regular intervals "
        "and spray as soon as chlorotic spots or mould are first seen. 2) Step up patrolling during "
        "overcast spells or when the relative humidity in the greenhouse stays above 90%. 3) Predict "
        "disease trends from temperature and humidity forecasts. 4) Watch for changes in the physiological "
        "races of the pathogen to guide rotation of resistant varieties."
    ),
    ("tomato_leaf_mold", "PHYSICAL"): (
        "1) Treat the seed with hot water. 2) Before transplanting, close the greenhouse or house for "
        "high-temperature solarisation (36-38 °C for 2 hours, or 30-35 °C for 3-4 hours). 3) Remove "
        "diseased lower leaves promptly and take them out of the field. 4) Before using the greenhouse, "
        "disinfect the trellis and the plastic film by sulphur fumigation."
    ),
    # ------------------------------------------------------------------
    # tomato_septoria_leaf_spot -- Septoria leaf spot
    # ------------------------------------------------------------------
    ("tomato_septoria_leaf_spot", "AGRICULTURAL"): (
        "1) Use disease-free seed or treat the seed (hot water at 52 °C for 30 minutes). 2) Rotate with "
        "non-solanaceous crops for 2-3 years. 3) Apply plenty of rotted organic manure and more phosphate "
        "and potash fertiliser. 4) Grow on raised beds with plastic film mulching to prevent rain splash. "
        "5) Remove diseased and old lower leaves in good time and, after harvest, clear crop residue "
        "completely and plough deeply."
    ),
    ("tomato_septoria_leaf_spot", "CHEMICAL"): (
        "Spray at the first sign of disease (when lesions are first seen or 5% of leaves are diseased), "
        "once every 7-10 days for 2-3 consecutive applications. Options are 70% mancozeb wettable powder "
        "at 500-600x (pre-harvest interval 15 days), 75% chlorothalonil wettable powder at 500-600x "
        "(pre-harvest interval 7 days), 10% difenoconazole water-dispersible granules at 1000-1500x "
        "(pre-harvest interval 7 days), 50% iprodione wettable powder at 1000x (pre-harvest interval 10 "
        "days), 70% thiophanate-methyl wettable powder at 800-1000x and 3% polyoxin aqueous solution at "
        "600-800x. Rotate protectants with systemic products and direct the spray at the lower leaves of "
        "the plant."
    ),
    ("tomato_septoria_leaf_spot", "ECOLOGICAL"): (
        "1) Use drip irrigation or subsurface drip under mulch, avoiding flood irrigation and rain splash. "
        "2) Apply biological preparations such as Bacillus subtilis and Trichoderma. 3) Use a sensible "
        "plant density and prune and remove suckers in good time to improve ventilation and light. "
        "4) Grow grass between the rows to lower field humidity."
    ),
    ("tomato_septoria_leaf_spot", "MONITORING"): (
        "1) From flowering and fruiting begin surveying the lower leaves at regular intervals. 2) Start "
        "fungicide control when the percentage of diseased leaves reaches 5%. 3) Check disease development "
        "promptly after rain. 4) Where possible monitor the release of pycnidia."
    ),
    ("tomato_septoria_leaf_spot", "PHYSICAL"): (
        "1) Treat the seed with hot water. 2) Use plastic film mulching to block splash dispersal of "
        "conidia from the soil. 3) Remove diseased lower leaves promptly and take them out of the field "
        "for deep burial. 4) After harvest clear crop residue completely and plough the soil deeply."
    ),
    # ------------------------------------------------------------------
    # tomato_two_spotted_spider_mite -- two-spotted spider mite
    # ------------------------------------------------------------------
    ("tomato_two_spotted_spider_mite", "AGRICULTURAL"): (
        "1) Clear weeds (such as goosefoot and plantain) in and around the field in good time to reduce "
        "overwintering and breeding hosts. 2) Plough the soil deeply in autumn and winter to kill "
        "overwintering female adults. 3) Irrigate sensibly and avoid drought; in greenhouses spray water "
        "to raise humidity as appropriate (RH above 60% can suppress mite reproduction). 4) Avoid "
        "excessive nitrogen and apply more phosphate and potash fertiliser to strengthen the plants' "
        "tolerance of the pest. 5) Use a sensible plant density, keeping the field ventilated and lit "
        "without becoming excessively dry."
    ),
    ("tomato_two_spotted_spider_mite", "CHEMICAL"): (
        "1) At the first sign of infestation treat spot by spot, targeting the centre of the mite focus. "
        "2) Fast-acting adulticides: 1.8% abamectin emulsifiable concentrate at 2000-3000x (poor against "
        "eggs, so best mixed with an ovicide). 3) Persistent ovicides: 24% spirodiclofen suspension "
        "concentrate at 3000-4000x (kills eggs and nymphs, with a residual period of 30-50 days) and 20% "
        "etoxazole suspension concentrate (kills eggs and newly hatched nymphs). 4) Products effective "
        "against both eggs and adults: 43% bifenazate suspension concentrate at 3000x (highly effective "
        "against all stages). 5) Direct the spray mainly at the underside of the leaves, ensuring even "
        "coverage, once every 7-10 days for 2 consecutive applications. 6) Rotate products with different "
        "modes of action (abamectin group, then spirodiclofen group, then bifenazate group) to delay "
        "resistance -- monitoring in the Beijing area shows that two-spotted spider mite has already "
        "developed fairly high resistance to abamectin and pyridaben, so rotation and mixtures must be "
        "used."
    ),
    ("tomato_two_spotted_spider_mite", "ECOLOGICAL"): (
        "1) Protect and release predatory mites: Phytoseiulus persimilis and Neoseiulus cucumeris, which "
        "work well when released at low mite density. 2) Protect natural enemies in the field such as "
        "lacewings, predatory ladybirds that feed on mites and six-spotted thrips. 3) Avoid applying "
        "broad-spectrum insecticides (such as pyrethroids) that kill natural enemies. 4) Plant cover crops "
        "around the greenhouse to improve the ecological microclimate."
    ),
    ("tomato_two_spotted_spider_mite", "MONITORING"): (
        "1) After transplanting survey the underside of the middle and lower leaves at regular intervals "
        "for mite density, checking once every 5 days. 2) Treat spot by spot at once when there are "
        "100-200 mites per 100 leaves or webbing is first seen. 3) Combined with forecasts of spells of "
        "high temperature and drought (temperature above 25 °C, RH below 60%), take preventive action in "
        "advance. 4) Check the older basal leaves first and deal with a centre of infestation at once to "
        "prevent it spreading."
    ),
    ("tomato_two_spotted_spider_mite", "PHYSICAL"): (
        "1) Fit insect-proof netting over the greenhouse vents. 2) Soil solarisation: during the fallow "
        "period close the greenhouse and raise the temperature to 35-38 °C for 2 hours, which can reduce "
        "overwintering mite numbers. 3) Hand-remove mite-infested old leaves at the base of the plant and "
        "destroy them centrally. 4) Water the greenhouse at the right time to raise humidity and suppress "
        "mite reproduction."
    ),
    # ------------------------------------------------------------------
    # tomato_target_spot -- target spot
    # ------------------------------------------------------------------
    ("tomato_target_spot", "AGRICULTURAL"): (
        "1) Rotate with non-host crops (graminaceous crops) for 2-3 years and avoid continuous cropping "
        "with cucumber or pepper. 2) Clear residue of the previous crop completely and plough deeply. "
        "3) Apply plenty of rotted organic manure, avoid excessive nitrogen and prevent the plants from "
        "growing excessively. 4) Use a sensible plant density and prune and remove suckers in good time to "
        "improve ventilation and light. 5) Use plastic film mulching and drip irrigation."
    ),
    ("tomato_target_spot", "CHEMICAL"): (
        "Spray before disease appears or when lesions are first seen, once every 10-14 days for 2-3 "
        "consecutive applications, ensuring even coverage of both leaf surfaces. Options are 75% "
        "chlorothalonil wettable powder at 500-600x (pre-harvest interval 7 days), 80% mancozeb wettable "
        "powder at 500-600x (pre-harvest interval 15 days), 10% difenoconazole water-dispersible granules "
        "at 1000-1500x (pre-harvest interval 7 days), 25% azoxystrobin suspension concentrate at "
        "1000-1500x (pre-harvest interval 5 days) and 50% iprodione wettable powder at 1000x (pre-harvest "
        "interval 10 days). Rotate protectants (chlorothalonil, mancozeb) with systemic products "
        "(difenoconazole, azoxystrobin) to delay resistance."
    ),
    ("tomato_target_spot", "ECOLOGICAL"): (
        "1) In protected cultivation improve ventilation and moisture removal, keeping relative humidity "
        "below 80%. 2) Apply biological preparations such as Trichoderma and Bacillus. 3) Use drip "
        "irrigation instead of flood irrigation. 4) Fertilise in a balanced way and avoid excessive growth "
        "and a closed, dense canopy."
    ),
    ("tomato_target_spot", "MONITORING"): (
        "1) After transplanting survey the leaves at regular intervals and spray as soon as target-like "
        "lesions are first seen. 2) Step up patrolling in hot, rainy seasons. 3) Take care to distinguish "
        "it from early blight and bacterial spot and avoid misdiagnosis. 4) Combined with weather "
        "forecasts, take preventive action in advance under high-humidity conditions."
    ),
    ("tomato_target_spot", "PHYSICAL"): (
        "1) Before transplanting, close the greenhouse or house and use high-temperature solarisation for "
        "disinfection. 2) Remove diseased leaves and fruit promptly and take them out of the field. "
        "3) Use plastic film mulching to block splash dispersal of the pathogen from the soil. 4) After "
        "harvest clear crop residue completely."
    ),
    # ------------------------------------------------------------------
    # tomato_mosaic_virus -- tomato mosaic virus
    # ------------------------------------------------------------------
    ("tomato_mosaic_virus", "AGRICULTURAL"): (
        "1) Choose resistant varieties (highly resistant TMV varieties such as the Jiafen and Zhongshu "
        "series). 2) Seed treatment: first soak the seed in clean water for 3-4 h, then soak it in 10% "
        "trisodium phosphate solution for 20-30 min, rinse it clean in water and then sprout it; or soak "
        "it in 0.1% potassium permanganate for 30 min. 3) Rotate with non-solanaceous crops for more than "
        "2 years. 4) Carry out operations on healthy plants before diseased ones; before pruning and "
        "removing suckers disinfect hands and tools with soapy water or 10% trisodium phosphate, and "
        "smokers must wash their hands with soap and change their work clothes before working. 5) Pull out "
        "early diseased plants promptly and take them out of the field for deep burial. 6) Strengthen "
        "fertilisation and irrigation management, applying more phosphate and potash fertiliser (0.3% "
        "monopotassium phosphate as a foliar spray) and avoiding excessive nitrogen, to increase the "
        "plants' tolerance of the disease."
    ),
    ("tomato_mosaic_virus", "CHEMICAL"): (
        "1) At the first sign of disease spray virus inhibitors such as moroxydine hydrochloride + copper "
        "(Virus A), amino-oligosaccharin and oligosaccharins and octylamine acetate, once every 7-10 days "
        "for 2-3 consecutive applications. 2) Spray zinc fertiliser (0.1% zinc sulphate) and monopotassium "
        "phosphate onto the leaves to increase the plants' tolerance of the disease. 3) Note that once TMV "
        "has entered the plant the effect of chemical treatment is limited; controlling the vector to "
        "prevent disease (preventing CMV) requires aphicides such as imidacloprid and thiamethoxam to be "
        "sprayed as well, but TMV itself does not depend on aphids."
    ),
    ("tomato_mosaic_virus", "ECOLOGICAL"): (
        "1) Ventilate and cool protected cultivation and avoid stress from high temperature and drought. "
        "2) Do not plant intermediate hosts such as tobacco or pepper around the greenhouse. 3) Apply "
        "biological virus inactivators such as lentinan and terpene alcohols. 4) Fertilise in a balanced "
        "way, applying more rotted organic manure and microbial fertiliser, to raise strong seedlings."
    ),
    ("tomato_mosaic_virus", "MONITORING"): (
        "1) From transplanting to flowering survey the percentage of diseased plants at regular intervals "
        "and pull out a primary infected plant at once. 2) Combined with forecasts of hot, dry weather, "
        "spray a protectant in advance. 3) Monitor the seedling stage as a priority and discard diseased "
        "seedlings at once. 4) Operate a separation system between the seedbed and the production field to "
        "prevent virus transmission by people."
    ),
    ("tomato_mosaic_virus", "PHYSICAL"): (
        "1) Dry-heat treatment of seed: treating seed with dry heat at 70 °C for 72 h can effectively "
        "remove seed-borne TMV. 2) Disinfect tools and hands with 10% trisodium phosphate or soapy water. "
        "3) Pull out diseased plants promptly and destroy them to reduce virus sources. 4) Lay silver-grey "
        "film to repel aphids (effective against CMV and indirectly reducing mixed infection)."
    ),
    # ------------------------------------------------------------------
    # tomato_yellow_leaf_curl_virus -- tomato yellow leaf curl virus
    # ------------------------------------------------------------------
    ("tomato_yellow_leaf_curl_virus", "AGRICULTURAL"): (
        "1) Choose TYLCV-resistant varieties (such as varieties carrying the Ty-1, Ty-2 and Ty-3 genes). "
        "2) Raise strong, insect-free seedlings: keep the seedling house separate from the production "
        "greenhouse and clear weeds and plant debris completely before raising seedlings. 3) Before "
        "transplanting clear weeds in and around the field completely to reduce bridging hosts. "
        "4) Transplant somewhat early to avoid the peak period of whitefly activity. 5) Strengthen "
        "fertilisation and irrigation management to bring the plants on early and increase their tolerance "
        "of the disease."
    ),
    ("tomato_yellow_leaf_curl_virus", "CHEMICAL"): (
        "The core strategy is to control the vector to prevent disease, that is, cutting off virus "
        "transmission by killing the whitefly. 1) Early in the whitefly infestation: alternate sprays of "
        "24% spirotetramat suspension concentrate at 2000x, 25% thiamethoxam water-dispersible granules at "
        "3000x and 10% nitenpyram aqueous solution at 1500x, once every 5-7 days for 2-3 consecutive "
        "applications. 2) When the population density is high: 10% cyantraniliprole oil-based suspension "
        "concentrate at 35-40 mL/mu, or 22.4% spirotetramat suspension concentrate at 17-20 mL/mu, or 20% "
        "dinotefuran soluble powder as a spray. 3) In protected cultivation 20% isoprocarb smoke generators "
        "may be used at 300-400 g/mu. 4) At the first sign of disease virus inhibitors such as "
        "amino-oligosaccharin and moroxydine hydrochloride may be sprayed to help relieve symptoms, but "
        "they cannot eradicate the disease. Take care to rotate products with different modes of action to "
        "delay whitefly resistance."
    ),
    ("tomato_yellow_leaf_curl_virus", "ECOLOGICAL"): (
        "1) Protect and release parasitic wasps such as Encarsia formosa and Eretmocerus spp. to control the "
        "whitefly. 2) Apply entomopathogenic fungi such as Metarhizium anisopliae and Beauveria bassiana. "
        "3) Plant trap crops (such as velvetleaf) around the greenhouse to trap and kill the pest in a "
        "concentrated area. 4) Avoid planting next to whitefly hosts such as cucumber and beans."
    ),
    ("tomato_yellow_leaf_curl_virus", "MONITORING"): (
        "1) From transplanting to fruit set monitor whitefly population density as a priority and spray at "
        "once when yellow sticky trap catches rise sharply. 2) The seedling stage is the key period for "
        "control: check the seedlings every week during the seedling-raising period for whitefly and for "
        "symptoms on new leaves. 3) Combined with forecasts of hot, dry weather, take preventive action "
        "across the board before the whitefly peak. 4) If new leaves showing yellowing and curling are "
        "found, trace the virus source at once and control the vector."
    ),
    ("tomato_yellow_leaf_curl_virus", "PHYSICAL"): (
        "1) Cover seedling and production greenhouses with 40-60 mesh insect-proof netting to keep the "
        "whitefly out. 2) Hang yellow sticky traps inside the greenhouse (20-30 traps/mu) to trap and kill "
        "adult whiteflies, with the bottom of the trap slightly above the plant growing point. 3) Fit "
        "insect-proof netting over the greenhouse vents and doorways. 4) Pull out severely diseased plants "
        "promptly and take them out of the field for destruction."
    ),
}
