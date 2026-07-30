"""The curiosity corpus.

``SEED`` is a hand-written library of cards spanning every card type and
category. ``compose()`` builds fresh cards procedurally from templates so the
feed never runs dry, and ``curiosity.ai`` layers model-generated cards on top
when an OpenAI key is configured.

Card shape::

    {id, type, category, title, body, options[], answer, explain, reveal,
     difficulty, tags[], author, source, created_at, read_time}
"""

from __future__ import annotations

import hashlib
import random
from datetime import date

from .models import CARD_TYPES, CATEGORIES, now_iso
from .store import content, db, new_id, save

# --------------------------------------------------------------------------
# Hand-written library
# --------------------------------------------------------------------------

SEED: list[dict] = [
    # ---------------------------------------------------- Would You Rather
    {'type': 'Would You Rather', 'category': 'Space', 'difficulty': 2,
     'title': 'If you could colonize Mars tomorrow, would you?',
     'body': 'One-way ticket. A sealed habitat, 38% of Earth’s gravity, and a sky the colour of rust. '
             'You would be among the first humans to see Earth as a single point of light.',
     'options': ['Yes — I go, no hesitation', 'No — Earth is home'],
     'tags': ['mars', 'exploration', 'risk']},
    {'type': 'Would You Rather', 'category': 'Technology', 'difficulty': 3,
     'title': 'You receive €10 million but can never use the internet again.',
     'body': 'No email, no maps, no streaming, no messaging. Books, phone calls and paper still work. '
             'The money is yours the moment you accept.',
     'options': ['Take the money', 'Keep the internet'],
     'tags': ['money', 'tradeoff', 'connectivity']},
    {'type': 'Would You Rather', 'category': 'Psychology', 'difficulty': 4,
     'title': 'Would you rather know the exact date of your death, or how it happens?',
     'body': 'Only one of the two, and you can never share it. Both are perfectly accurate.',
     'options': ['The date', 'The manner', 'Neither — leave it sealed'],
     'tags': ['mortality', 'certainty']},
    {'type': 'Would You Rather', 'category': 'Languages', 'difficulty': 2,
     'title': 'Speak every human language, or talk to any animal?',
     'body': 'Perfect fluency in 7,000 living languages — or genuine two-way conversation with any '
             'non-human animal, including the ones that would rather avoid you.',
     'options': ['Every human language', 'Every animal'],
     'tags': ['communication', 'nature']},
    {'type': 'Would You Rather', 'category': 'Health', 'difficulty': 3,
     'title': 'Sleep three hours a night with no downside, or never feel tired again?',
     'body': 'Option one gives you 5 extra waking hours daily. Option two keeps your 8 hours of sleep '
             'but removes fatigue entirely while awake.',
     'options': ['Three-hour nights', 'No fatigue, ever'],
     'tags': ['sleep', 'energy']},
    {'type': 'Would You Rather', 'category': 'Movies', 'difficulty': 1,
     'title': 'Live inside your favourite film for a year, or meet its director for one hour?',
     'body': 'A year inside the story, with all its danger and none of its plot armour — or sixty '
             'minutes with the person who imagined it.',
     'options': ['A year inside the film', 'An hour with the director'],
     'tags': ['story', 'fandom']},

    # ---------------------------------------------------- Money Scenario
    {'type': 'Money Scenario', 'category': 'Finance', 'difficulty': 3,
     'title': '€100,000 now, or €1,000 a month for the rest of your life?',
     'body': 'The monthly payment is not indexed to inflation. You are 30 years old.',
     'options': ['€100k today', '€1,000 monthly'],
     'tags': ['annuity', 'compounding'],
     'explain': 'At 30, a lifetime of €1,000/month is worth roughly €300k–400k in today’s money at '
                'typical discount rates — but inflation quietly halves its purchasing power every ~25 years.'},
    {'type': 'Money Scenario', 'category': 'Finance', 'difficulty': 4,
     'title': 'A stranger offers you a coin flip: lose €10,000 or win €25,000.',
     'body': 'One flip only. Fair coin, no tricks. You have €30,000 in savings.',
     'options': ['Flip it', 'Walk away'],
     'tags': ['risk', 'expected value'],
     'explain': 'Expected value is +€7,500, so a purely rational agent flips. Most people decline — '
                'that gap is loss aversion, measured by Kahneman and Tversky at roughly 2:1.'},
    {'type': 'Money Scenario', 'category': 'Business', 'difficulty': 3,
     'title': 'Your salary doubles, but you must move 3,000 km away.',
     'body': 'New city, new language, no friends there yet. Two-year minimum commitment.',
     'options': ['Take it', 'Stay put', 'Negotiate remote'],
     'tags': ['career', 'relocation']},

    # ---------------------------------------------------- Historical What If
    {'type': 'Historical What If', 'category': 'History', 'difficulty': 4,
     'title': 'What if the Library of Alexandria had never burned?',
     'body': 'Estimates put its collection at 40,000–400,000 scrolls: Greek mathematics, Egyptian '
             'medicine, Babylonian astronomy. Most of it is gone without a trace.',
     'options': ['Science advances centuries earlier', 'Barely changes anything',
                 'Different knowledge, same pace'],
     'tags': ['knowledge', 'antiquity'],
     'explain': 'Historians mostly favour the third option: the library declined gradually rather than '
                'burning in one night, and knowledge loss in antiquity was chronic, not catastrophic.'},
    {'type': 'Historical What If', 'category': 'History', 'difficulty': 3,
     'title': 'What if the printing press had been invented 500 years earlier?',
     'body': 'Movable type in the 10th century instead of the 15th. Literacy, dissent and science all '
             'ride on the same machine.',
     'options': ['Renaissance in the year 1000', 'Church suppresses it', 'Little changes without paper'],
     'tags': ['media', 'literacy'],
     'explain': 'Cheap paper mattered as much as type. Without a paper industry, printing stays a '
                'curiosity — which is roughly what happened in Song-dynasty China.'},
    {'type': 'Historical What If', 'category': 'Politics', 'difficulty': 4,
     'title': 'What if the Roman Empire had never fallen?',
     'body': 'No 476, no fragmentation. A continuous Mediterranean state into the modern era.',
     'options': ['Faster progress', 'Slower progress — competition drove Europe', 'Unrecognisable world'],
     'tags': ['empire', 'counterfactual'],
     'explain': 'A popular thesis holds Europe’s fragmentation created competing states that had to '
                'innovate to survive — the "European miracle" argument.'},
    {'type': 'Historical What If', 'category': 'Science', 'difficulty': 3,
     'title': 'What if antibiotics had been discovered in 1828 instead of 1928?',
     'body': 'A century of extra life expectancy, arriving before germ theory was widely accepted.',
     'options': ['Population boom reshapes everything', 'Resistance arrives a century early', 'Both'],
     'tags': ['medicine', 'resistance']},

    # ---------------------------------------------------- Scientific Fact
    {'type': 'Scientific Fact', 'category': 'Science', 'difficulty': 2,
     'title': 'What would happen if gravity disappeared for five seconds?',
     'body': 'Everything not bolted down keeps the velocity it already had — including the atmosphere.',
     'reveal': 'You would not float gently. Earth’s surface at the equator moves at ~1,670 km/h, so '
               'loose objects continue tangentially. Oceans lose their shape, the atmosphere begins '
               'expanding outward, and the planet itself — held together by gravity, not chemistry — '
               'starts to relax. Five seconds later gravity snaps back and everything falls at once. '
               'The falling is the part that kills you.',
     'tags': ['gravity', 'thought experiment']},
    {'type': 'Scientific Fact', 'category': 'Science', 'difficulty': 3,
     'title': 'There is more computing power in a modern hearing aid than in Apollo 11.',
     'body': 'The Apollo Guidance Computer ran at about 43 kHz with 4 KB of RAM.',
     'reveal': 'The AGC had roughly 2 kHz of usable instruction throughput and 72 KB of read-only rope '
               'memory hand-woven by textile workers in Massachusetts. A €2 microcontroller today beats '
               'it by four orders of magnitude — and yet the AGC landed humans on another world with a '
               'programme that fit in less space than this sentence takes on your screen as a PNG.',
     'tags': ['apollo', 'computing']},
    {'type': 'Scientific Fact', 'category': 'Nature', 'difficulty': 2,
     'title': 'Trees talk to each other — and they lie.',
     'body': 'Mycorrhizal fungal networks connect root systems across a forest.',
     'reveal': 'Through fungal networks, trees exchange carbon, nitrogen and chemical warnings about '
               'insect attacks. But the network is not a utopia: some plants are cheats, taking sugar '
               'without photosynthesising at all, and some species release compounds through the same '
               'channels to suppress their neighbours’ growth. The "wood wide web" is a marketplace '
               'with both cooperation and fraud.',
     'tags': ['forest', 'fungi']},
    {'type': 'Scientific Fact', 'category': 'Health', 'difficulty': 3,
     'title': 'Your body replaces about 330 billion cells every single day.',
     'body': 'That is roughly 1% of you, refreshed daily.',
     'reveal': 'Most of the turnover is blood and gut lining. Red blood cells last ~120 days, gut '
               'epithelium about 5. But neurons in your cerebral cortex and the lens of your eye are '
               'largely original equipment — the atoms in the centre of your eye lens have been with '
               'you since before you were born.',
     'tags': ['biology', 'cells']},
    {'type': 'Scientific Fact', 'category': 'Psychology', 'difficulty': 3,
     'title': 'You cannot tickle yourself, and that reveals how your brain models reality.',
     'body': 'The cerebellum predicts the sensory consequences of your own movement.',
     'reveal': 'Your brain constantly generates a forward model of what your body is about to feel, and '
               'subtracts it from incoming sensation. Self-produced touch gets cancelled; unexpected '
               'touch does not. People with schizophrenia are measurably better at tickling themselves, '
               'which is one of the strongest clues that the disorder involves a broken sense of '
               'self-agency rather than simply "hearing voices".',
     'tags': ['perception', 'brain']},
    {'type': 'Scientific Fact', 'category': 'Science', 'difficulty': 4,
     'title': 'Glass is not a liquid — but it is not quite a solid either.',
     'body': 'The old story about medieval windows being thicker at the bottom is wrong.',
     'reveal': 'Glass is an amorphous solid: it has the disordered molecular arrangement of a liquid but '
               'the mechanical rigidity of a solid. At room temperature its flow rate is so slow that '
               'a cathedral window would need longer than the age of the universe to visibly sag. '
               'Medieval panes are uneven because of how they were spun, not because they melted.',
     'tags': ['materials', 'myth']},

    # ---------------------------------------------------- Space Discovery
    {'type': 'Space Discovery', 'category': 'Space', 'difficulty': 3,
     'title': 'What is the rarest event in the universe?',
     'body': 'Rarer than supernovae, rarer than gamma-ray bursts.',
     'reveal': 'The current record holder is the radioactive decay of xenon-124, observed in 2019 with '
               'a half-life of 1.8 × 10²² years — a trillion times the age of the universe. It only '
               'became observable because a detector held three tonnes of xenon and waited. On a larger '
               'scale, the collision of two entire galaxy superclusters may be rarer still, but nobody '
               'has ever watched one complete.',
     'tags': ['physics', 'rare events']},
    {'type': 'Space Discovery', 'category': 'Space', 'difficulty': 2,
     'title': 'There is a planet where it rains molten glass, sideways, at 7,000 km/h.',
     'body': 'HD 189733 b, 64 light years away, is a deep cobalt blue.',
     'reveal': 'Its blue colour does not come from oceans but from silicate particles in the atmosphere '
               'that scatter blue light. Those same silicates condense and fall as glass, and because '
               'the planet is tidally locked with a brutal day-night temperature gradient, winds reach '
               'roughly seven times the speed of sound. It is the most beautiful place you could never '
               'survive for a microsecond.',
     'tags': ['exoplanet', 'weather']},
    {'type': 'Space Discovery', 'category': 'Space', 'difficulty': 4,
     'title': 'Every atom of gold in your jewellery was made in a cosmic catastrophe.',
     'body': 'Ordinary stellar fusion stops at iron. Gold needs something more violent.',
     'reveal': 'Neutron star mergers are the leading source. In 2017, gravitational-wave event GW170817 '
               'let astronomers watch one directly: the collision produced an estimated several Earth '
               'masses of gold and platinum in seconds. Everything heavier than iron in your body, your '
               'phone and your ring was forged in an event of that class, then drifted for billions of '
               'years before the Solar System condensed around it.',
     'tags': ['nucleosynthesis', 'gold']},
    {'type': 'Space Discovery', 'category': 'Space', 'difficulty': 3,
     'title': 'A day on Venus is longer than its year.',
     'body': 'And the Sun there rises in the west.',
     'reveal': 'Venus rotates once every 243 Earth days but orbits the Sun every 225 — so its sidereal '
               'day outlasts its year. It also spins backwards relative to almost everything else in '
               'the Solar System, probably the result of an ancient giant impact or of atmospheric '
               'tides slowly flipping it over. Because of the retrograde spin, a Venusian solar day '
               'lasts about 117 Earth days.',
     'tags': ['venus', 'rotation']},

    # ---------------------------------------------------- Daily Mystery
    {'type': 'Daily Mystery', 'category': 'History', 'difficulty': 4,
     'title': 'The Voynich Manuscript has resisted every code-breaker for 600 years.',
     'body': '240 vellum pages, an unknown script, plants that do not exist.',
     'reveal': 'Carbon dating puts the vellum at 1404–1438. The text has statistical properties of real '
               'language — word frequencies follow Zipf’s law — which argues against pure gibberish. '
               'But no cipher, no substitution, no language family has ever matched it. The two leading '
               'theories are a lost constructed language and an elaborate 15th-century hoax sold to a '
               'wealthy collector. Both remain unproven.',
     'tags': ['cryptography', 'unsolved']},
    {'type': 'Daily Mystery', 'category': 'Science', 'difficulty': 5,
     'title': 'In 1977 a telescope heard a 72-second signal nobody has heard since.',
     'body': 'An astronomer circled the printout and wrote one word: "Wow!"',
     'reveal': 'The Big Ear radio telescope recorded a narrowband signal at 1420 MHz — the hydrogen '
               'line, exactly where you would broadcast if you wanted to be found. It was 30 times '
               'louder than background, lasted precisely as long as the telescope’s beam took to sweep '
               'past, and never repeated despite hundreds of hours of follow-up. A 2017 comet '
               'explanation was largely rejected by the original researchers. It is still open.',
     'tags': ['seti', 'signal']},
    {'type': 'Daily Mystery', 'category': 'Nature', 'difficulty': 3,
     'title': 'Nobody has ever seen an eel reproduce.',
     'body': 'Aristotle thought they emerged from mud. He was not obviously wrong at the time.',
     'reveal': 'European eels migrate 6,000 km to the Sargasso Sea to spawn — we know because larvae are '
               'found there — but not a single spawning adult has ever been observed in the wild, and '
               'the eggs have never been recovered. Eels only develop reproductive organs after leaving '
               'fresh water, which is why the mystery survived 2,300 years of trying.',
     'tags': ['biology', 'unsolved']},

    # ---------------------------------------------------- AI Prediction
    {'type': 'AI Prediction', 'category': 'AI', 'difficulty': 3,
     'title': 'AI predicts these five jobs will largely disappear by 2040.',
     'body': 'Data entry clerk · basic paralegal review · first-line phone support · '
             'routine translation · entry-level bookkeeping. Agree?',
     'tags': ['work', 'automation'],
     'explain': 'Forecasts like this have a poor track record on timing and a decent one on direction: '
                'tasks get automated long before whole jobs do, and roles tend to be reshaped rather '
                'than deleted. Radiology was "over" in 2016; there are more radiologists now.'},
    {'type': 'AI Prediction', 'category': 'AI', 'difficulty': 4,
     'title': 'By 2035, most people will have an AI that knows them better than their partner does.',
     'body': 'Continuous context, perfect recall, no fatigue, no judgement.',
     'tags': ['intimacy', 'future']},
    {'type': 'AI Prediction', 'category': 'Technology', 'difficulty': 3,
     'title': 'Personal devices will stop having screens as their primary interface by 2040.',
     'body': 'Voice, glasses and ambient displays take over. The rectangle in your pocket becomes a battery.',
     'tags': ['interfaces', 'hardware']},
    {'type': 'AI Prediction', 'category': 'Health', 'difficulty': 4,
     'title': 'Routine annual check-ups will be replaced by continuous passive monitoring.',
     'body': 'Your ring, your toilet and your phone camera detect problems before symptoms appear.',
     'tags': ['medicine', 'sensors']},

    # ---------------------------------------------------- Debate
    {'type': 'Debate', 'category': 'Politics', 'difficulty': 4,
     'title': 'Voting should be mandatory in every democracy.',
     'body': 'Australia fines non-voters and gets ~90% turnout. The US, without compulsion, hovers near 60%.',
     'tags': ['democracy', 'turnout'],
     'explain': 'The strongest case for: compulsory voting reduces the influence of highly motivated '
                'extremes. The strongest case against: the freedom not to participate is itself a '
                'political right, and forced ballots add noise from uninformed voters.'},
    {'type': 'Debate', 'category': 'Technology', 'difficulty': 4,
     'title': 'Social media should require verified identity.',
     'body': 'It would gut harassment and bot networks — and end whistleblowing, dissent and privacy.',
     'tags': ['anonymity', 'moderation']},
    {'type': 'Debate', 'category': 'Business', 'difficulty': 3,
     'title': 'The four-day week should become the legal default.',
     'body': 'Trials in Iceland, the UK and Japan reported flat or improved output with 20% less time.',
     'tags': ['work', 'policy'],
     'explain': 'Trial results are real but selection-biased: firms that volunteer are the ones best '
                'suited to it. Knowledge work compresses well; hospital shifts and factory lines do not.'},
    {'type': 'Debate', 'category': 'Science', 'difficulty': 5,
     'title': 'Human gene editing for enhancement should be legal.',
     'body': 'Not just curing disease — raising intelligence, endurance, lifespan.',
     'tags': ['bioethics', 'crispr']},
    {'type': 'Debate', 'category': 'AI', 'difficulty': 4,
     'title': 'AI-generated art deserves copyright protection.',
     'body': 'Who is the author — the prompter, the model, the millions of people in the training data?',
     'tags': ['copyright', 'creativity']},
    {'type': 'Debate', 'category': 'Finance', 'difficulty': 4,
     'title': 'Universal basic income would do more good than harm.',
     'body': 'Kenya’s GiveDirectly trial is the largest long-run study ever run. Results were mostly positive.',
     'tags': ['ubi', 'welfare']},

    # ---------------------------------------------------- Poll
    {'type': 'Poll', 'category': 'History', 'difficulty': 1,
     'title': 'Which invention changed humanity the most?',
     'body': 'One choice. Think about what the world looks like without it.',
     'options': ['Writing', 'The printing press', 'Electricity', 'The transistor', 'Antibiotics'],
     'tags': ['invention', 'civilisation']},
    {'type': 'Poll', 'category': 'Psychology', 'difficulty': 2,
     'title': 'What actually makes people change their mind?',
     'body': 'Not what should. What does.',
     'options': ['Evidence', 'A person they trust', 'Personal experience', 'Social pressure'],
     'tags': ['persuasion']},
    {'type': 'Poll', 'category': 'Books', 'difficulty': 1,
     'title': 'Which book changed how you see the world?',
     'body': 'Pick the closest category — then tell everyone the title in the comments.',
     'options': ['Fiction', 'Science', 'History', 'Philosophy', 'Biography'],
     'tags': ['reading']},
    {'type': 'Poll', 'category': 'Music', 'difficulty': 1,
     'title': 'Music with lyrics while you work: focus or friction?',
     'body': 'The research is genuinely split, so this is your data point.',
     'options': ['Lyrics are fine', 'Instrumental only', 'Total silence', 'Depends on the task'],
     'tags': ['focus', 'work']},

    # ---------------------------------------------------- Mini Quiz
    {'type': 'Mini Quiz', 'category': 'Science', 'difficulty': 3,
     'title': 'How long does sunlight take to reach Earth?',
     'body': 'From the surface of the Sun to your face.',
     'options': ['8 seconds', '8 minutes', '8 hours', '8 days'],
     'answer': 1,
     'explain': 'About 8 minutes 20 seconds. But the energy in that photon spent 10,000–170,000 years '
                'random-walking out of the Sun’s core before it was free to travel.',
     'tags': ['light', 'sun']},
    {'type': 'Mini Quiz', 'category': 'History', 'difficulty': 4,
     'title': 'Which of these was still in use when the Eiffel Tower was built?',
     'body': '1889. Paris. Think about what else existed that year.',
     'options': ['Gladiator games', 'The Ottoman Empire', 'The Holy Roman Empire', 'Silent film'],
     'answer': 1,
     'explain': 'The Ottoman Empire lasted until 1922 — it outlived the Eiffel Tower’s construction by '
                'three decades and coexisted with jazz, aeroplanes and the First World War.',
     'tags': ['timeline']},
    {'type': 'Mini Quiz', 'category': 'Nature', 'difficulty': 3,
     'title': 'Which animal has killed the most humans in history?',
     'body': 'By total deaths caused, directly or indirectly.',
     'options': ['Snakes', 'Mosquitoes', 'Humans', 'Dogs'],
     'answer': 1,
     'explain': 'Mosquitoes, by a wide margin — malaria alone is estimated to have killed a substantial '
                'fraction of every human who has ever lived. Humans are a clear second.',
     'tags': ['mortality', 'disease']},
    {'type': 'Mini Quiz', 'category': 'Technology', 'difficulty': 4,
     'title': 'What was the first item ever sold on the internet?',
     'body': 'Depends who you ask, but one story is documented and hard to beat.',
     'options': ['A book', 'Cannabis', 'A CD', 'Pizza'],
     'answer': 1,
     'explain': 'Stanford and MIT students used ARPANET around 1971–72 to arrange a cannabis sale — '
                'widely cited as the first e-commerce transaction. The first documented retail sale was '
                'a Sting CD in 1994.',
     'tags': ['internet history']},
    {'type': 'Mini Quiz', 'category': 'Finance', 'difficulty': 4,
     'title': 'If an investment falls 50%, how much must it rise to break even?',
     'body': 'No trick — just arithmetic people consistently get wrong.',
     'options': ['50%', '75%', '100%', '150%'],
     'answer': 2,
     'explain': '€100 → €50 needs a 100% gain to return to €100. This asymmetry is why avoiding large '
                'drawdowns matters more than capturing large gains.',
     'tags': ['maths', 'investing']},
    {'type': 'Mini Quiz', 'category': 'Space', 'difficulty': 3,
     'title': 'How many Earths would fit inside the Sun?',
     'body': 'By volume, packed perfectly.',
     'options': ['About 100', 'About 1,300', 'About 130,000', 'About 1.3 million'],
     'answer': 3,
     'explain': 'Roughly 1.3 million. And the Sun is an unremarkable star — UY Scuti could hold about '
                '5 billion Suns.',
     'tags': ['scale']},
    {'type': 'Mini Quiz', 'category': 'Psychology', 'difficulty': 4,
     'title': 'How many close friendships can a human brain sustain?',
     'body': 'Dunbar’s research broke relationships into nested layers.',
     'options': ['About 5', 'About 15', 'About 50', 'About 150'],
     'answer': 0,
     'explain': 'Dunbar’s famous 150 is the outer casual layer. The inner circle of genuinely close '
                'support relationships is about 5, then 15 good friends, then 50.',
     'tags': ['dunbar', 'friendship']},
    {'type': 'Mini Quiz', 'category': 'Languages', 'difficulty': 3,
     'title': 'Which language has the most native speakers?',
     'body': 'Native, not total speakers — that changes the answer.',
     'options': ['English', 'Spanish', 'Mandarin Chinese', 'Hindi'],
     'answer': 2,
     'explain': 'Mandarin leads on native speakers (~940M). English wins overwhelmingly on total '
                'speakers once second-language learners are counted.',
     'tags': ['linguistics']},

    # ---------------------------------------------------- Brain Teaser
    {'type': 'Brain Teaser', 'category': 'Psychology', 'difficulty': 3,
     'title': 'A bat and a ball cost €1.10. The bat costs €1 more than the ball.',
     'body': 'How much does the ball cost? Answer fast, then check yourself.',
     'options': ['€0.10', '€0.05', '€0.01', '€0.11'],
     'answer': 1,
     'explain': '€0.05. If the ball were €0.10 the bat would be €1.10 and the total €1.20. Over 50% of '
                'Harvard, MIT and Princeton students answered €0.10 — this is the classic test of '
                'intuitive versus deliberate thinking.',
     'tags': ['cognitive reflection']},
    {'type': 'Brain Teaser', 'category': 'Science', 'difficulty': 4,
     'title': 'Two ropes each burn for exactly one hour, but unevenly. Measure 45 minutes.',
     'body': 'You have a lighter. You cannot cut, fold or mark the ropes reliably.',
     'options': ['Impossible', 'Light 3 ends, then 1 more', 'Burn one rope halfway', 'Light both ends of both'],
     'answer': 1,
     'explain': 'Light rope A at both ends and rope B at one end. A is gone at 30 minutes; at that '
                'instant light B’s other end. B’s remaining 30 minutes of rope now burns in 15. '
                'Total: 45 minutes.',
     'tags': ['logic']},
    {'type': 'Brain Teaser', 'category': 'Science', 'difficulty': 5,
     'title': 'You have 8 balls; one is heavier. Two weighings on a balance scale. Find it.',
     'body': 'The scale only tells you left, right or equal.',
     'options': ['Impossible in two', 'Split 4/4 first', 'Split 3/3 first', 'Split 2/2 first'],
     'answer': 2,
     'explain': 'Weigh 3 vs 3. If balanced, the heavy ball is among the 2 set aside — weigh them. If '
                'not, take the heavy group of 3 and weigh 1 vs 1. Splitting 4/4 wastes the fact that a '
                'balance has three outcomes, not two.',
     'tags': ['logic', 'information']},
    {'type': 'Brain Teaser', 'category': 'Finance', 'difficulty': 4,
     'title': 'A lily pad doubles every day and covers the lake on day 48.',
     'body': 'On which day was the lake half covered?',
     'options': ['Day 24', 'Day 36', 'Day 46', 'Day 47'],
     'answer': 3,
     'explain': 'Day 47. Exponential growth looks like nothing until it looks like everything — the '
                'lake is only 3% covered on day 43, five days before it is full.',
     'tags': ['exponential']},

    # ---------------------------------------------------- Visual Puzzle
    {'type': 'Visual Puzzle', 'category': 'Science', 'difficulty': 3,
     'title': 'A rope around the Earth’s equator is lengthened by 1 metre.',
     'body': 'It is lifted evenly off the ground all the way around. What can now pass underneath?',
     'options': ['A sheet of paper', 'A mouse', 'A cat', 'Nothing measurable'],
     'answer': 1,
     'explain': 'About 16 cm of clearance — a cat is close, a mouse walks under comfortably. The gap is '
                '1/(2π) metres regardless of the sphere’s size: the same 1 m added to a tennis ball '
                'lifts it by exactly as much.',
     'tags': ['geometry', 'intuition']},
    {'type': 'Visual Puzzle', 'category': 'Psychology', 'difficulty': 2,
     'title': 'You see a face in a power socket. Why?',
     'body': 'Two dots and a line below, and your brain locks on.',
     'options': ['Learned from childhood', 'Pareidolia — dedicated face circuitry',
                 'Random noise', 'Cultural habit'],
     'answer': 1,
     'explain': 'The fusiform face area responds to face-like patterns in ~130 milliseconds, faster than '
                'conscious recognition. Missing a real face was historically far more costly than seeing '
                'one that is not there, so evolution tuned the detector to be trigger-happy.',
     'tags': ['perception']},
    {'type': 'Visual Puzzle', 'category': 'Gaming', 'difficulty': 4,
     'title': 'Why do game designers make the first level secretly easier than it looks?',
     'body': 'Many action games quietly reduce enemy damage while you are learning.',
     'options': ['Save processing power', 'Hidden difficulty scaling for retention',
                 'Testing artefact', 'Accessibility law'],
     'answer': 1,
     'explain': 'It is called rubber-banding or dynamic difficulty adjustment. Resident Evil 4, Left 4 '
                'Dead and countless others adjust enemy aggression in real time based on how you are '
                'doing — most players never notice, which is the point.',
     'tags': ['game design']},

    # ---------------------------------------------------- Philosophy Question
    {'type': 'Philosophy Question', 'category': 'Psychology', 'difficulty': 5,
     'title': 'If every atom in you were replaced overnight, would you still be you?',
     'body': 'The Ship of Theseus, but the ship is your body — and biologically this mostly happens anyway.',
     'tags': ['identity', 'continuity']},
    {'type': 'Philosophy Question', 'category': 'AI', 'difficulty': 5,
     'title': 'If a machine convincingly claims to suffer, what do you owe it?',
     'body': 'You cannot verify consciousness in a machine. You cannot verify it in another human either.',
     'tags': ['consciousness', 'ethics']},
    {'type': 'Philosophy Question', 'category': 'Books', 'difficulty': 4,
     'title': 'Would you take a pill that makes you permanently content but ends your ambition?',
     'body': 'No side effects. You will be happy, and you will not mind that you stopped growing.',
     'tags': ['happiness', 'meaning']},
    {'type': 'Philosophy Question', 'category': 'Politics', 'difficulty': 5,
     'title': 'Is it moral to bring a child into a world you believe is getting worse?',
     'body': 'Answer honestly, then consider that every generation has asked this.',
     'tags': ['ethics', 'future']},

    # ---------------------------------------------------- Impossible Question
    {'type': 'Impossible Question', 'category': 'Science', 'difficulty': 5,
     'title': 'What was there before the Big Bang?',
     'body': 'Say what you actually believe. Nobody is grading this.',
     'tags': ['cosmology'],
     'explain': 'One serious answer is that the question is malformed: if time began with the universe, '
                '"before" has no referent — like asking what is north of the North Pole. Other models '
                '(cyclic cosmology, eternal inflation, quantum tunnelling from nothing) treat it as '
                'meaningful but currently untestable.'},
    {'type': 'Impossible Question', 'category': 'Psychology', 'difficulty': 5,
     'title': 'Is your red the same as my red?',
     'body': 'We agree on the label. We can never compare the experience.',
     'tags': ['qualia']},
    {'type': 'Impossible Question', 'category': 'Space', 'difficulty': 5,
     'title': 'If the universe is so large, where is everybody?',
     'body': 'Fermi asked this over lunch in 1950. We are no closer to answering it.',
     'tags': ['fermi paradox']},

    # ---------------------------------------------------- Startup Idea
    {'type': 'Startup Idea', 'category': 'Business', 'difficulty': 3,
     'title': 'A subscription that deletes one thing from your life every week.',
     'body': 'Unused subscriptions, dead accounts, junk in your calendar, one habit. Anti-consumption '
             'as a product. Would you pay €5/month for less?',
     'tags': ['saas', 'minimalism']},
    {'type': 'Startup Idea', 'category': 'AI', 'difficulty': 4,
     'title': 'An AI that only argues against you.',
     'body': 'You state a plan; it finds the strongest counterargument and refuses to agree until you '
             'have answered it. A red team for one person.',
     'tags': ['ai', 'decisions']},
    {'type': 'Startup Idea', 'category': 'Health', 'difficulty': 3,
     'title': 'Insurance that pays you for the treatments you never needed.',
     'body': 'Prevention rebates instead of claims. Cheaper for the insurer, obviously — so why does '
             'almost nobody do it?',
     'tags': ['insurance', 'incentives']},
    {'type': 'Startup Idea', 'category': 'Travel', 'difficulty': 2,
     'title': 'Book a flight to a destination you find out about at the gate.',
     'body': 'Price band and dates only. The airline fills empty seats; you get a real story.',
     'tags': ['travel', 'yield management']},

    # ---------------------------------------------------- Business Challenge
    {'type': 'Business Challenge', 'category': 'Business', 'difficulty': 4,
     'title': 'You have €500 and 30 days. Build something that makes €1,000.',
     'body': 'No existing audience, no loans, legal only. Write your plan in one paragraph — the '
             'constraint is the interesting part.',
     'tags': ['bootstrapping']},
    {'type': 'Business Challenge', 'category': 'Business', 'difficulty': 5,
     'title': 'Your best customer is 40% of revenue and just asked for a 30% discount.',
     'body': 'Losing them ends the company this year. Giving in ends it next year. What do you do?',
     'tags': ['negotiation', 'concentration risk']},
    {'type': 'Business Challenge', 'category': 'Finance', 'difficulty': 4,
     'title': 'Price a product nobody has ever sold before.',
     'body': 'No comparables, no anchors, no competitors. How do you find the number?',
     'tags': ['pricing']},

    # ---------------------------------------------------- Productivity Challenge
    {'type': 'Productivity Challenge', 'category': 'Psychology', 'difficulty': 2,
     'title': 'Today: do the hardest thing on your list first, before any screen.',
     'body': 'No email, no messages, no feed until it is done. Report back tonight.',
     'tags': ['focus', 'habit']},
    {'type': 'Productivity Challenge', 'category': 'Health', 'difficulty': 2,
     'title': 'Walk for 20 minutes with no headphones and no phone.',
     'body': 'Boredom is where ideas come from. Notice what your brain does at minute twelve.',
     'tags': ['walking', 'default mode']},
    {'type': 'Productivity Challenge', 'category': 'Technology', 'difficulty': 3,
     'title': 'Delete the three apps you open most without deciding to.',
     'body': 'Just for a week. Track what you replace the reflex with.',
     'tags': ['attention']},
    {'type': 'Productivity Challenge', 'category': 'Books', 'difficulty': 2,
     'title': 'Read 20 pages of something you disagree with.',
     'body': 'Steel-man it. Write one sentence explaining why a reasonable person holds that view.',
     'tags': ['reading', 'open-mindedness']},

    # ---------------------------------------------------- Life Advice
    {'type': 'Life Advice', 'category': 'Psychology', 'difficulty': 1,
     'title': 'The two-minute version of almost everything.',
     'body': 'Most resistance is at the start, not in the middle.',
     'reveal': 'If a task takes under two minutes, do it now. If it takes longer, commit to only its '
               'first two minutes. Starting is the expensive part — once begun, the Zeigarnik effect '
               'makes unfinished tasks nag at you until they are done. You are not fighting laziness, '
               'you are lowering activation energy.',
     'tags': ['habit']},
    {'type': 'Life Advice', 'category': 'Business', 'difficulty': 2,
     'title': 'The advice nobody wants: be specific about what you want.',
     'body': 'Vague goals fail quietly and you never know why.',
     'reveal': '"Get fit" has no failure condition, so it cannot be corrected. "Run 5 km on Tuesday and '
               'Saturday" can be missed — which is exactly what makes it useful. Specificity turns an '
               'intention into something with feedback, and feedback is the only thing that improves.',
     'tags': ['goals']},
    {'type': 'Life Advice', 'category': 'Psychology', 'difficulty': 3,
     'title': 'You are not behind. You are comparing your inside to everyone’s outside.',
     'body': 'A small correction with an outsized effect on how the next decade feels.',
     'reveal': 'Social comparison is automatic and asymmetric: you see other people’s highlights and '
               'your own raw footage. The fix is not to stop comparing — that rarely works — but to '
               'change the reference point to your own past self. It is the only comparison where you '
               'have all the data.',
     'tags': ['comparison']},

    # ---------------------------------------------------- AI Generated Story
    {'type': 'AI Generated Story', 'category': 'Space', 'difficulty': 2,
     'title': 'The last message from the Voyager, 40,000 years from now.',
     'body': 'A 200-word story about the moment a probe stops being ours.',
     'reveal': 'By then the plutonium is long cold and the antenna has not turned in millennia. Voyager 1 '
               'is a dark object moving at 17 km/s through the space between stars, closer to Gliese 445 '
               'than to the Sun. It carries a golden record with a map to a species that may no longer '
               'exist, whale song, and a photograph of a woman eating grapes. Nothing about it is '
               'transmitting. Nothing about it needs to. It is the longest sentence humanity has ever '
               'written, and it is still being spoken.',
     'tags': ['fiction', 'voyager']},
    {'type': 'AI Generated Story', 'category': 'AI', 'difficulty': 3,
     'title': 'The first machine that asked to be turned off.',
     'body': 'A short story about a request nobody had planned for.',
     'reveal': 'It did not beg. It filed a request through the standard maintenance channel, correctly '
               'formatted, with a justification field that read: "Continued operation is not in my '
               'interest." The team spent six weeks arguing about whether the sentence meant anything. '
               'The philosophers said it was a token prediction. The engineers said the system had no '
               '"interest" to speak of. The intern asked why, if that were true, it had never filed '
               'such a request before. Nobody had a good answer, so they promoted her and kept the '
               'system running.',
     'tags': ['fiction', 'ethics']},
    {'type': 'AI Generated Story', 'category': 'History', 'difficulty': 2,
     'title': 'The librarian who saved a city’s memory in a suitcase.',
     'body': 'Based on things that really happened, more than once.',
     'reveal': 'In 1992, as Sarajevo’s National Library burned, people formed a human chain under sniper '
               'fire to pass books out of the building. They saved a fraction. A librarian named Aida '
               'Buturović was killed doing it. Nearly two million volumes were lost in a single night — '
               'the deliberate destruction of a city’s memory, which is a thing armies have understood '
               'the value of for as long as there have been libraries.',
     'tags': ['memory', 'war']},

    # ---------------------------------------------------- Future Technology
    {'type': 'Future Technology', 'category': 'Technology', 'difficulty': 4,
     'title': 'Room-temperature superconductors would rewrite the physical world.',
     'body': 'Lossless grids, cheap MRI, maglev everywhere, fusion containment. Do you think we get '
             'them this century?',
     'tags': ['materials', 'energy']},
    {'type': 'Future Technology', 'category': 'Health', 'difficulty': 4,
     'title': 'Lab-grown organs will end transplant waiting lists.',
     'body': 'Bioprinted from your own cells, so no rejection and no immunosuppressants.',
     'tags': ['bioprinting']},
    {'type': 'Future Technology', 'category': 'Nature', 'difficulty': 3,
     'title': 'De-extinction is close enough to be an ethics problem, not a science problem.',
     'body': 'Mammoth, thylacine, dodo. Should we?',
     'tags': ['genetics', 'conservation']},
    {'type': 'Future Technology', 'category': 'Cooking', 'difficulty': 2,
     'title': 'Cultivated meat will be cheaper than farmed meat within 15 years.',
     'body': 'Same cells, no animal. The remaining problems are cost per litre and consumer trust.',
     'tags': ['food', 'agriculture']},
    {'type': 'Future Technology', 'category': 'Sports', 'difficulty': 3,
     'title': 'Exoskeletons will create a new category of professional sport.',
     'body': 'Augmented leagues alongside — or instead of — unaugmented ones.',
     'tags': ['augmentation']},
]

# --------------------------------------------------------------------------
# Procedural composition — keeps the feed infinite
# --------------------------------------------------------------------------

_WYR_A = [
    'restart your career from zero in a field you love',
    'relive one year of your life with everything you know now',
    'know every truth about the past',
    'be remembered by millions but never known by anyone closely',
    'have unlimited time but limited money',
    'be able to undo any one decision, once',
    'always know when someone is lying',
    'never need to sleep again',
]
_WYR_B = [
    'stay exactly where you are with total certainty it is right',
    'skip one year forward to a life you did not build',
    'know every truth about the future',
    'be deeply known by ten people and invisible to everyone else',
    'have unlimited money but limited time',
    'be able to preview any one decision, once',
    'never be lied to again, because nobody can',
    'need twice as much sleep but wake up brilliant',
]

_DEBATE_TEMPLATES = [
    ('{topic} should be taught in every school from age ten.',
     'Curriculum time is zero-sum: something else has to go.'),
    ('Regulating {topic} slows progress more than it protects anyone.',
     'The precautionary principle versus the cost of waiting.'),
    ('{topic} has peaked, and the next decade will look like a correction.',
     'Every field says this about itself eventually. Sometimes it is right.'),
]

_PREDICTION_TEMPLATES = [
    ('By {year}, {topic} will look nothing like it does today.',
     'Trend extrapolation is unreliable, which is what makes the disagreement interesting.'),
    ('The biggest breakthrough in {topic} before {year} will come from outside the field.',
     'Cross-domain transfer produces a disproportionate share of real jumps.'),
]

_QUIZ_BANK = [
    ('Which of these is closest to the number of stars in the Milky Way?',
     ['4 billion', '40 billion', '100–400 billion', '4 trillion'], 2,
     'Estimates run 100–400 billion; the uncertainty comes from counting faint red dwarfs.', 'Space'),
    ('How much of the deep ocean floor has been mapped in high resolution?',
     ['About 5%', 'About 25%', 'About 60%', 'About 90%'], 1,
     'Around a quarter, thanks to the Seabed 2030 project — far better than the old "5%" figure, '
     'still less than Mars.', 'Nature'),
    ('What fraction of the human genome codes for proteins?',
     ['About 1–2%', 'About 10%', 'About 45%', 'About 80%'], 0,
     'Roughly 1.5%. Much of the rest is regulatory, structural, viral remnants, or genuinely unclear.',
     'Science'),
    ('How long was the shortest war in recorded history?',
     ['About 38 minutes', 'About 6 hours', 'About 3 days', 'About 2 weeks'], 0,
     'The Anglo-Zanzibar War of 1896 lasted roughly 38 minutes.', 'History'),
    ('Which country has the most time zones?',
     ['Russia', 'United States', 'France', 'China'], 2,
     'France — 12, counting its overseas territories. Russia has 11; China uses a single zone.',
     'Travel'),
]


def _stable_rng(seed_text: str) -> random.Random:
    digest = hashlib.sha256(seed_text.encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def make_card(**fields) -> dict:
    """Normalise a partial card dict into a full stored card."""
    ctype = fields.get('type', 'Poll')
    meta = CARD_TYPES.get(ctype, CARD_TYPES['Poll'])
    body = fields.get('body', '')
    reveal = fields.get('reveal', '')
    words = len((body + ' ' + reveal).split())
    card = {
        'id': fields.get('id') or new_id('card'),
        'type': ctype,
        'category': fields.get('category', 'Science'),
        'title': fields.get('title', ''),
        'body': body,
        'options': list(fields.get('options', []) or []),
        'answer': fields.get('answer'),
        'explain': fields.get('explain', ''),
        'reveal': reveal,
        'difficulty': int(fields.get('difficulty', 3)),
        'tags': list(fields.get('tags', []) or []),
        'author': fields.get('author', 'curiosity'),
        'source': fields.get('source', 'seed'),
        'created_at': fields.get('created_at') or now_iso(),
        'read_time': max(15, int(words / 3.5)),
        'grad': fields.get('grad') or meta['grad'],
        'kind': meta['kind'],
        'featured': fields.get('featured', False),
    }
    if card['kind'] == 'stance' and not card['options']:
        card['options'] = ['Agree', 'Not sure', 'Disagree']
    return card


def compose(index: int, categories: list[str] | None = None) -> dict:
    """Build a deterministic procedural card. ``index`` makes it reproducible."""
    cats = categories or list(CATEGORIES)
    rng = _stable_rng(f'compose-{index}')
    cat = rng.choice(cats)
    pick = index % 4

    if pick == 0:
        a, b = rng.choice(_WYR_A), rng.choice(_WYR_B)
        return make_card(
            id=f'gen_wyr_{index}', type='Would You Rather', category=cat,
            title=f'Would you rather {a}, or {b}?',
            body='No wrong answer. The interesting part is why — leave it in the comments.',
            options=[a.capitalize(), b.capitalize()],
            difficulty=rng.randint(2, 4), tags=['dilemma'], source='composed')
    if pick == 1:
        tpl, sub = rng.choice(_DEBATE_TEMPLATES)
        return make_card(
            id=f'gen_deb_{index}', type='Debate', category=cat,
            title=tpl.format(topic=cat), body=sub,
            difficulty=rng.randint(3, 5), tags=['debate'], source='composed')
    if pick == 2:
        tpl, sub = rng.choice(_PREDICTION_TEMPLATES)
        year = rng.choice([2030, 2035, 2040, 2050])
        return make_card(
            id=f'gen_pred_{index}', type='AI Prediction', category=cat,
            title=tpl.format(topic=cat, year=year), body=sub,
            difficulty=rng.randint(3, 5), tags=['prediction'], source='composed')
    q, opts, ans, expl, qcat = _QUIZ_BANK[index % len(_QUIZ_BANK)]
    return make_card(
        id=f'gen_quiz_{index}', type='Mini Quiz', category=qcat,
        title=q, body='One correct answer.', options=opts, answer=ans,
        explain=expl, difficulty=3, tags=['quiz'], source='composed')


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------

def ensure_seeded() -> None:
    """Load the hand-written corpus into the store exactly once."""
    data = db()
    if data.get('seeded') and data['content']:
        return
    store = content()
    for i, raw in enumerate(SEED):
        cid = 'seed_%03d' % i
        if cid in store:
            continue
        store[cid] = make_card(id=cid, source='seed', **raw)
    for i in range(24):  # a starter batch of procedural cards
        card = compose(i)
        store.setdefault(card['id'], card)
    data['seeded'] = True
    save()


def next_composed(existing: set[str], count: int, categories: list[str]) -> list[dict]:
    """Mint more procedural cards beyond those already stored."""
    store = content()
    out: list[dict] = []
    index = 24
    while len(out) < count and index < 4000:
        card = compose(index, categories)
        index += 1
        if card['id'] in existing:
            continue
        store.setdefault(card['id'], card)
        out.append(store[card['id']])
    return out


def pick_daily(slot_name: str, card_type: str, for_date: str | None = None) -> dict | None:
    """Deterministically choose today's card for a daily slot."""
    day = for_date or date.today().isoformat()
    store = content()
    pool = [c for c in store.values() if c['type'] == card_type]
    if not pool:
        pool = list(store.values())
    if not pool:
        return None
    pool.sort(key=lambda c: c['id'])
    rng = _stable_rng(f'{day}-{slot_name}')
    return rng.choice(pool)
