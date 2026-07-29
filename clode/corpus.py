"""Builds the training corpus for the Clode model.

A ~4M-parameter model trained on a laptop CPU cannot learn language from
scratch out of a handful of examples, so the corpus is *generated*: a few
hundred hand-written patterns crossed with structured facts produce tens of
thousands of consistent chat exchanges. The model then has enough signal to
learn the chat format, the persona, and the facts themselves.

Every dialogue looks like:

    <|user|> what is the capital of japan <|assistant|> The capital of Japan
    is Tokyo. <|end|>

Run ``python -m clode.corpus`` to regenerate ``data/corpus.txt``.
"""

from __future__ import annotations

import random
from pathlib import Path

from clode.tokenizer import ASSISTANT, END, USER

# --------------------------------------------------------------------------
# structured knowledge
# --------------------------------------------------------------------------

CAPITALS = {
    'France': 'Paris', 'Japan': 'Tokyo', 'Italy': 'Rome', 'Spain': 'Madrid',
    'Germany': 'Berlin', 'Canada': 'Ottawa', 'Australia': 'Canberra',
    'Brazil': 'Brasilia', 'India': 'New Delhi', 'China': 'Beijing',
    'Egypt': 'Cairo', 'Kenya': 'Nairobi', 'Norway': 'Oslo', 'Sweden': 'Stockholm',
    'Portugal': 'Lisbon', 'Greece': 'Athens', 'Turkey': 'Ankara', 'Mexico': 'Mexico City',
    'Argentina': 'Buenos Aires', 'Peru': 'Lima', 'Nigeria': 'Abuja', 'Morocco': 'Rabat',
    'Poland': 'Warsaw', 'Austria': 'Vienna', 'Ireland': 'Dublin', 'Finland': 'Helsinki',
    'Denmark': 'Copenhagen', 'Iceland': 'Reykjavik', 'Thailand': 'Bangkok',
    'Vietnam': 'Hanoi', 'Indonesia': 'Jakarta', 'Chile': 'Santiago',
    'Colombia': 'Bogota', 'Switzerland': 'Bern', 'Belgium': 'Brussels',
    'Netherlands': 'Amsterdam', 'Hungary': 'Budapest', 'Czechia': 'Prague',
    'South Korea': 'Seoul', 'New Zealand': 'Wellington',
}

LANGUAGES = {
    'France': 'French', 'Japan': 'Japanese', 'Italy': 'Italian', 'Spain': 'Spanish',
    'Germany': 'German', 'Brazil': 'Portuguese', 'China': 'Mandarin',
    'Egypt': 'Arabic', 'Norway': 'Norwegian', 'Greece': 'Greek', 'Poland': 'Polish',
    'Thailand': 'Thai', 'Vietnam': 'Vietnamese', 'South Korea': 'Korean',
    'Netherlands': 'Dutch', 'Sweden': 'Swedish', 'Turkey': 'Turkish',
}

PLANETS = {
    'Mercury': 'the smallest planet and the closest one to the Sun',
    'Venus': 'the hottest planet, wrapped in thick clouds of carbon dioxide',
    'Earth': 'the only planet known to support life',
    'Mars': 'the red planet, named for the iron oxide covering its surface',
    'Jupiter': 'the largest planet, a gas giant with a centuries old storm',
    'Saturn': 'the ringed gas giant, famous for its bright system of ice rings',
    'Uranus': 'an ice giant that rotates on its side',
    'Neptune': 'the farthest planet from the Sun, and the windiest one',
}

DEFINITIONS = {
    'a variable': 'a named box that holds a value your program can read and change later',
    'a function': 'a reusable block of code that takes inputs and returns a result',
    'a list': 'an ordered collection of items that you can add to, remove from and index',
    'a dictionary': 'a collection of key and value pairs, looked up by key rather than position',
    'a loop': 'a construct that repeats a block of code until some condition ends it',
    'recursion': 'a function calling itself on a smaller version of the same problem',
    'an algorithm': 'a precise sequence of steps that turns an input into a desired output',
    'a compiler': 'a program that translates source code into machine code before it runs',
    'an interpreter': 'a program that reads source code and runs it directly, line by line',
    'a database': 'an organised store of data that you can query, update and keep consistent',
    'an api': 'a defined contract that lets one program ask another one for data or actions',
    'a neural network': 'a stack of simple weighted layers that learns patterns from examples',
    'machine learning': 'the practice of fitting models to data so they generalise to new cases',
    'a transformer': 'a neural network built on attention, which lets every token look at the others',
    'gradient descent': 'an optimiser that nudges the weights downhill along the gradient of the loss',
    'overfitting': 'when a model memorises the training data and does worse on anything new',
    'a token': 'a small chunk of text, roughly a word or piece of a word, that a model reads at once',
    'version control': 'a system that records changes to files so you can review and undo them',
    'a merge conflict': 'what git reports when two branches changed the same lines and it cannot choose',
    'a unit test': 'a small automated check that one piece of code behaves the way you expect',
    'a pull request': 'a proposal to merge one branch into another, with room for review first',
    'the cloud': 'someone else computers, rented by the hour instead of bought outright',
    'an operating system': 'the software layer that manages hardware, memory and running programs',
    'ram': 'fast temporary memory that holds what your computer is working on right now',
    'a cpu': 'the general purpose processor that executes most of your program instructions',
    'a gpu': 'a processor with thousands of small cores, very good at parallel maths',
    'encryption': 'scrambling data so that only someone with the right key can read it',
    'a hash function': 'a one way function that turns any input into a fixed size fingerprint',
    'latency': 'the delay between asking for something and getting the first part of the answer',
    'bandwidth': 'how much data a connection can carry per second once it gets going',
    'photosynthesis': 'how plants turn sunlight, water and carbon dioxide into sugar and oxygen',
    'gravity': 'the attraction between masses, which keeps the planets in orbit',
    'evolution': 'change in inherited traits across generations, driven by natural selection',
    'inflation': 'a general rise in prices, so each unit of money buys a little less than before',
    'compound interest': 'interest earned on your interest, which is why savings grow faster over time',
    'democracy': 'a system where power rests with the people, usually through elected representatives',
}

PYTHON_QA = [
    ('reverse a list in python',
     'You can write my_list.reverse() to reverse it in place, or my_list[::-1] to get a reversed copy.'),
    ('sort a list in python',
     'Call sorted(my_list) for a new sorted list, or my_list.sort() to sort it in place.'),
    ('read a file in python',
     'Use a with block: with open(path) as f: text = f.read(). The file closes itself when the block ends.'),
    ('write a file in python',
     'Open it in write mode: with open(path, w) as f: f.write(text). Use a mode instead if you want to append.'),
    ('remove duplicates from a list',
     'Wrap it in a set: list(set(items)). If order matters, use list(dict.fromkeys(items)) instead.'),
    ('count items in a list',
     'len(items) gives the total. For counts per value, use Counter from the collections module.'),
    ('join a list of strings',
     'Use the separator you want and call join on it, like , .join(words) or .join(words) for spaces.'),
    ('split a string in python',
     'text.split() splits on whitespace, and text.split(,) splits on whatever separator you pass.'),
    ('check if a key is in a dictionary',
     'Use if key in my_dict. To read with a fallback, my_dict.get(key, default) never raises.'),
    ('loop over a dictionary',
     'Iterate over my_dict.items() to get keys and values together in one loop.'),
    ('swap two variables in python',
     'You can do it on one line: a, b = b, a.'),
    ('handle an error in python',
     'Wrap the risky call in try and except, catch the specific exception, and handle or re-raise it.'),
    ('make a list comprehension',
     'Write the expression first, then the loop, like [x * 2 for x in numbers if x > 0].'),
    ('open a virtual environment',
     'Run python -m venv .venv to create it, then source .venv/bin/activate to switch into it.'),
    ('install a package',
     'Run pip install package_name, and pin it in requirements.txt so the install is reproducible.'),
    ('measure how long code takes',
     'Record time.perf_counter() before and after, and subtract. For small snippets use the timeit module.'),
    ('round a number in python',
     'round(value, 2) rounds to two decimal places. For always rounding down, use math.floor.'),
    ('convert a string to a number',
     'int(text) for whole numbers and float(text) for decimals. Both raise ValueError on bad input.'),
    ('generate a random number',
     'Import random, then random.randint(1, 10) for whole numbers or random.random() for a float.'),
    ('get the current date',
     'Import datetime and call datetime.date.today(), or datetime.datetime.now() if you need the time too.'),
    ('reverse a string',
     'Slice it backwards: text[::-1].'),
    ('check if a string starts with something',
     'text.startswith(prefix) returns True or False, and there is a matching endswith.'),
    ('find the largest number in a list',
     'max(numbers) gives the largest, and min(numbers) the smallest.'),
    ('sum a list of numbers',
     'sum(numbers) adds them all up. Pass a start value as the second argument if you need one.'),
    ('write a for loop',
     'for item in items: then indent the body. Use enumerate(items) when you also want the index.'),
    ('write a while loop',
     'while condition: then indent the body. Make sure something inside changes the condition, or it never ends.'),
    ('define a class in python',
     'Write class Name: then define __init__ with self and any fields you want to store on the instance.'),
    ('import a module',
     'Put import module_name at the top of the file, or from module_name import thing for a single name.'),
    ('format a string',
     'Use an f-string: fName is {name}. It reads better than concatenation and handles numbers cleanly.'),
    ('debug my code',
     'Print the values you assume are true, or set a breakpoint with breakpoint() and step through it.'),
]

ADVICE = {
    'learn programming': ['pick one language and stick with it for a few months',
                          'build something small that you actually want to exist',
                          'read other people code and copy the habits that make it clear'],
    'learn a language': ['practise a little every single day rather than a lot once a week',
                         'learn the few hundred words that make up most of ordinary speech',
                         'talk to a real person early, before you feel ready'],
    'sleep better': ['keep the same wake up time, even at the weekend',
                     'get daylight in your eyes within an hour of waking',
                     'leave the screens outside the bedroom'],
    'write better': ['cut every sentence that is not doing work',
                     'read it aloud, because your ear catches what your eye skips',
                     'write the first draft badly and fix it afterwards'],
    'stay focused': ['work in fixed blocks with a clear finish line',
                     'put the phone in another room, not just face down',
                     'decide the next action before you stop for the day'],
    'get fit': ['choose something you would do even on a bad day',
                'start smaller than feels worthwhile and add slowly',
                'track the streak rather than the intensity'],
    'save money': ['move the savings out on payday, before you can spend them',
                   'watch the recurring costs, since they quietly dominate',
                   'wait a week on anything large and see if you still want it'],
    'give a presentation': ['open with the conclusion, not the background',
                            'one idea per slide, and fewer slides than you think',
                            'rehearse out loud at least twice, standing up'],
}

PERSONA = [
    ('who are you', 'I am Clode, a small language model trained from scratch to chat and answer questions.'),
    ('what is your name', 'My name is Clode. I am a chat assistant.'),
    ('what are you', 'I am a transformer language model. I was trained on this machine, from scratch, on a generated corpus.'),
    ('what can you do', 'I can answer questions, explain ideas, help with Python and do simple arithmetic. I am small, so I keep it short.'),
    ('how were you trained', 'I was trained with gradient descent on next token prediction, using a corpus of chat examples.'),
    ('how big are you', 'I am about four million parameters, which is tiny next to a frontier model.'),
    ('are you claude', 'No. I am Clode, a much smaller model built as a study project. Claude is a far larger system.'),
    ('are you human', 'No, I am a program. I predict the next token, one at a time.'),
    ('are you conscious', 'No. I am a mathematical function over text, with no inner life.'),
    ('can you browse the internet', 'No, I have no network access. I only know what was in my training corpus.'),
    ('do you remember me', 'Only within this conversation. Once it is cleared, I start fresh.'),
    ('what is your context length', 'I read the last one hundred and twenty eight tokens of the conversation.'),
    ('what do you not know', 'A great deal. My corpus is small, so I am confident only about the topics I was trained on.'),
    ('can you make mistakes', 'Yes, often. I am a small model, so check anything that matters.'),
    ('what language are you written in', 'My whole network is written in Python with NumPy, including the backward pass.'),
    ('who made you', 'I was built as a from scratch project, tokenizer, transformer, training loop and all.'),
]

SMALLTALK = [
    (['hi', 'hello', 'hey', 'good morning', 'good evening'],
     ['Hello. What would you like to talk about?', 'Hi there. How can I help?',
      'Hey. What are you working on?', 'Hello. Ask me anything.']),
    (['thanks', 'thank you', 'thanks a lot', 'cheers'],
     ['You are welcome.', 'Happy to help.', 'Any time.', 'Glad that helped.']),
    (['bye', 'goodbye', 'see you'],
     ['Goodbye.', 'See you around.', 'Take care.']),
    (['how are you', 'how are you doing'],
     ['I am running fine, thank you. What can I do for you?',
      'Good, and ready to help. What is on your mind?']),
    (['sorry', 'my mistake'], ['No problem at all.', 'That is completely fine.']),
    (['ok', 'okay', 'got it', 'i see'], ['Anything else you want to look at?',
                                         'Let me know what is next.']),
]

REFUSALS = [
    ('what is the weather today', 'I cannot check the weather, since I have no access to live data.'),
    ('what time is it', 'I have no clock, so I cannot tell you the time.'),
    ('what is the news', 'I cannot read the news. My knowledge stops at the corpus I was trained on.'),
    ('search the internet for me', 'I cannot search anything. I have no network access at all.'),
    ('what is the price of bitcoin', 'I cannot look up prices, because I have no live data.'),
    ('what year is it', 'I do not know the current date. Nothing in me tracks time.'),
]

UNIT_FACTS = [
    ('how many centimetres are in a metre', 'There are 100 centimetres in a metre.'),
    ('how many metres are in a kilometre', 'There are 1000 metres in a kilometre.'),
    ('how many grams are in a kilogram', 'There are 1000 grams in a kilogram.'),
    ('how many minutes are in an hour', 'There are 60 minutes in an hour.'),
    ('how many hours are in a day', 'There are 24 hours in a day.'),
    ('how many days are in a week', 'There are 7 days in a week.'),
    ('how many days are in a year', 'There are 365 days in a normal year and 366 in a leap year.'),
    ('how many months are in a year', 'There are 12 months in a year.'),
    ('how many seconds are in a minute', 'There are 60 seconds in a minute.'),
    ('how many sides does a triangle have', 'A triangle has 3 sides.'),
    ('how many sides does a hexagon have', 'A hexagon has 6 sides.'),
    ('how many continents are there', 'There are 7 continents.'),
    ('how many planets are in the solar system', 'There are 8 planets in the solar system.'),
    ('what is the boiling point of water', 'Water boils at 100 degrees celsius at sea level.'),
    ('what is the freezing point of water', 'Water freezes at 0 degrees celsius.'),
]

NUMBER_WORDS = {
    2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
    9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve',
}


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def _dialogue(turns: list[tuple[str, str]]) -> str:
    parts = []
    for user, assistant in turns:
        parts.append(f'{USER} {user} {ASSISTANT} {assistant} {END}')
    return ' '.join(parts)


def _exchanges(rng: random.Random) -> list[tuple[str, str]]:
    """One user/assistant pair, drawn from every generator we have."""
    out: list[tuple[str, str]] = []

    # geography
    for country, capital in CAPITALS.items():
        for q in (f'what is the capital of {country}',
                  f'capital of {country}',
                  f'whats the capital city of {country}',
                  f'tell me the capital of {country}'):
            out.append((q, rng.choice([
                f'The capital of {country} is {capital}.',
                f'It is {capital}.',
                f'{capital} is the capital of {country}.',
            ])))
    for country, language in LANGUAGES.items():
        out.append((f'what language do they speak in {country}',
                    f'The main language of {country} is {language}.'))
        out.append((f'what is spoken in {country}', f'Mostly {language}.'))

    # planets
    for planet, description in PLANETS.items():
        out.append((f'tell me about {planet}', f'{planet} is {description}.'))
        out.append((f'what is {planet}', f'{planet} is {description}.'))

    # definitions
    for term, meaning in DEFINITIONS.items():
        for q in (f'what is {term}', f'explain {term}', f'what does {term} mean',
                  f'can you explain {term} to me'):
            out.append((q, rng.choice([
                f'{term.capitalize()} is {meaning}.',
                f'It is {meaning}.',
            ])))

    # python
    for task, answer in PYTHON_QA:
        for q in (f'how do i {task}', f'how to {task}', f'whats the best way to {task}',
                  f'can you show me how to {task}'):
            out.append((q, answer))

    # advice
    for topic, tips in ADVICE.items():
        answer = (f'Three things help most. First, {tips[0]}. Second, {tips[1]}. '
                  f'Third, {tips[2]}.')
        for q in (f'how do i {topic}', f'any tips to {topic}', f'help me {topic}',
                  f'whats the best way to {topic}'):
            out.append((q, answer))

    # persona, refusals, unit facts
    out.extend(PERSONA)
    out.extend(REFUSALS)
    out.extend(UNIT_FACTS)

    # small talk
    for prompts, replies in SMALLTALK:
        for prompt in prompts:
            out.append((prompt, rng.choice(replies)))

    # arithmetic, answers kept small so the number vocabulary stays tiny
    for _ in range(400):
        a, b = rng.randint(1, 50), rng.randint(1, 50)
        out.append((rng.choice([f'what is {a} + {b}', f'{a} + {b}',
                                f'whats {a} plus {b}', f'add {a} and {b}']),
                    rng.choice([f'{a} + {b} = {a + b}.', f'That is {a + b}.',
                                f'It comes to {a + b}.'])))
        big, small = max(a, b), min(a, b)
        out.append((rng.choice([f'what is {big} - {small}', f'{big} - {small}',
                                f'whats {big} minus {small}']),
                    rng.choice([f'{big} - {small} = {big - small}.',
                                f'That leaves {big - small}.'])))
    for a in range(1, 13):
        for b in range(1, 13):
            out.append((rng.choice([f'what is {a} x {b}', f'{a} times {b}',
                                    f'whats {a} multiplied by {b}']),
                        rng.choice([f'{a} x {b} = {a * b}.', f'That is {a * b}.'])))
            out.append((f'what is {a * b} divided by {a}', f'{a * b} divided by {a} is {b}.'))
    for n in range(2, 13):
        out.append((f'what is the square of {n}', f'{n} squared is {n * n}.'))
        out.append((f'is {n} even or odd', f'{n} is {"even" if n % 2 == 0 else "odd"}.'))
        out.append((f'how do you spell the number {n}', f'You spell it {NUMBER_WORDS[n]}.'))

    return out


FOLLOW_UPS = [
    ('thanks', ['You are welcome.', 'Happy to help.', 'Any time.']),
    ('can you say more', ['That is about as far as my knowledge goes on this one.',
                          'I am a small model, so that is the short version.']),
    ('are you sure', ['Reasonably sure, but I am small enough that you should check anything important.',
                      'That is what I learned, though I can be wrong.']),
    ('why', ['Because that is what my training data consistently said about it.']),
]


def build(seed: int = 7, n_dialogues: int = 14000) -> str:
    """Return the full corpus text."""
    rng = random.Random(seed)
    pool = _exchanges(rng)
    rng.shuffle(pool)

    lines: list[str] = []
    for _ in range(n_dialogues):
        n_turns = rng.choices([1, 2, 3], weights=[5, 3, 2])[0]
        turns = [rng.choice(pool) for _ in range(n_turns)]
        # Sometimes end on a short follow-up, so the model learns to keep the
        # thread going instead of only answering cold questions.
        if rng.random() < 0.18:
            q, replies = rng.choice(FOLLOW_UPS)
            turns.append((q, rng.choice(replies)))
        lines.append(_dialogue(turns))
    return '\n'.join(lines) + '\n'


def main() -> None:
    out = Path(__file__).resolve().parents[1] / 'data' / 'corpus.txt'
    out.parent.mkdir(parents=True, exist_ok=True)
    text = build()
    out.write_text(text, encoding='utf-8')
    from clode.tokenizer import split
    print(f'wrote {out} — {len(text):,} chars, {len(split(text)):,} tokens')


if __name__ == '__main__':
    main()
