"""Builds the training corpus for the Clode model.

A ~4M-parameter model trained on a laptop CPU cannot learn language from
scratch out of a handful of examples, so the corpus is *generated*: a few
hundred hand-written patterns crossed with structured facts produce hundreds
of thousands of consistent chat exchanges. The model then has enough signal
to learn the chat format, the persona, and the facts themselves.

Every dialogue looks like:

    <|user|> what is the capital of japan <|assistant|> The capital of Japan
    is Tokyo. <|end|>

Facts that need associative recall (country to capital, element to symbol)
are the hardest thing for a model this small to learn, so ``WEIGHTS`` below
oversamples those categories rather than relying on a uniform draw.

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
    'Portugal': 'Lisbon', 'Greece': 'Athens', 'Turkey': 'Ankara',
    'Mexico': 'Mexico City', 'Argentina': 'Buenos Aires', 'Peru': 'Lima',
    'Nigeria': 'Abuja', 'Morocco': 'Rabat', 'Poland': 'Warsaw', 'Austria': 'Vienna',
    'Ireland': 'Dublin', 'Finland': 'Helsinki', 'Denmark': 'Copenhagen',
    'Iceland': 'Reykjavik', 'Thailand': 'Bangkok', 'Vietnam': 'Hanoi',
    'Indonesia': 'Jakarta', 'Chile': 'Santiago', 'Colombia': 'Bogota',
    'Switzerland': 'Bern', 'Belgium': 'Brussels', 'Netherlands': 'Amsterdam',
    'Hungary': 'Budapest', 'Czechia': 'Prague', 'South Korea': 'Seoul',
    'New Zealand': 'Wellington', 'Ukraine': 'Kyiv', 'Romania': 'Bucharest',
    'Bulgaria': 'Sofia', 'Croatia': 'Zagreb', 'Serbia': 'Belgrade',
    'Slovakia': 'Bratislava', 'Slovenia': 'Ljubljana', 'Estonia': 'Tallinn',
    'Latvia': 'Riga', 'Lithuania': 'Vilnius', 'Ethiopia': 'Addis Ababa',
    'Ghana': 'Accra', 'Tanzania': 'Dodoma', 'Uganda': 'Kampala',
    'Algeria': 'Algiers', 'Tunisia': 'Tunis', 'Senegal': 'Dakar',
    'Pakistan': 'Islamabad', 'Bangladesh': 'Dhaka', 'Nepal': 'Kathmandu',
    'Sri Lanka': 'Colombo', 'Malaysia': 'Kuala Lumpur', 'Singapore': 'Singapore',
    'Philippines': 'Manila', 'Cambodia': 'Phnom Penh', 'Mongolia': 'Ulaanbaatar',
    'Iraq': 'Baghdad', 'Iran': 'Tehran', 'Jordan': 'Amman', 'Lebanon': 'Beirut',
    'Israel': 'Jerusalem', 'Cuba': 'Havana', 'Jamaica': 'Kingston',
    'Panama': 'Panama City', 'Uruguay': 'Montevideo', 'Paraguay': 'Asuncion',
    'Bolivia': 'La Paz', 'Ecuador': 'Quito', 'Venezuela': 'Caracas',
    'Costa Rica': 'San Jose', 'Guatemala': 'Guatemala City',
}

LANGUAGES = {
    'France': 'French', 'Japan': 'Japanese', 'Italy': 'Italian', 'Spain': 'Spanish',
    'Germany': 'German', 'Brazil': 'Portuguese', 'China': 'Mandarin',
    'Egypt': 'Arabic', 'Norway': 'Norwegian', 'Greece': 'Greek', 'Poland': 'Polish',
    'Thailand': 'Thai', 'Vietnam': 'Vietnamese', 'South Korea': 'Korean',
    'Netherlands': 'Dutch', 'Sweden': 'Swedish', 'Turkey': 'Turkish',
    'Portugal': 'Portuguese', 'Russia': 'Russian', 'Israel': 'Hebrew',
    'Iran': 'Persian', 'Finland': 'Finnish', 'Hungary': 'Hungarian',
    'Indonesia': 'Indonesian', 'Kenya': 'Swahili', 'Ukraine': 'Ukrainian',
}

CONTINENTS = {
    'France': 'Europe', 'Japan': 'Asia', 'Brazil': 'South America',
    'Egypt': 'Africa', 'Australia': 'Oceania', 'Canada': 'North America',
    'India': 'Asia', 'Kenya': 'Africa', 'Mexico': 'North America',
    'Norway': 'Europe', 'Chile': 'South America', 'Nigeria': 'Africa',
    'Thailand': 'Asia', 'New Zealand': 'Oceania', 'Peru': 'South America',
    'Germany': 'Europe', 'China': 'Asia', 'Morocco': 'Africa',
}

CURRENCIES = {
    'Japan': 'the yen', 'United Kingdom': 'the pound', 'France': 'the euro',
    'Germany': 'the euro', 'India': 'the rupee', 'China': 'the yuan',
    'Mexico': 'the peso', 'Sweden': 'the krona', 'Switzerland': 'the franc',
    'Poland': 'the zloty', 'Turkey': 'the lira', 'South Korea': 'the won',
    'Brazil': 'the real', 'Israel': 'the shekel', 'Denmark': 'the krone',
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

ELEMENTS = {
    'hydrogen': ('H', 1), 'helium': ('He', 2), 'lithium': ('Li', 3),
    'carbon': ('C', 6), 'nitrogen': ('N', 7), 'oxygen': ('O', 8),
    'sodium': ('Na', 11), 'magnesium': ('Mg', 12), 'aluminium': ('Al', 13),
    'silicon': ('Si', 14), 'phosphorus': ('P', 15), 'sulfur': ('S', 16),
    'chlorine': ('Cl', 17), 'potassium': ('K', 19), 'calcium': ('Ca', 20),
    'iron': ('Fe', 26), 'copper': ('Cu', 29), 'zinc': ('Zn', 30),
    'silver': ('Ag', 47), 'tin': ('Sn', 50), 'gold': ('Au', 79),
    'mercury': ('Hg', 80), 'lead': ('Pb', 82), 'uranium': ('U', 92),
}

SUPERLATIVES = {
    'the largest ocean': 'The Pacific is the largest ocean.',
    'the longest river': 'The Nile and the Amazon are the longest rivers, depending on how you measure them.',
    'the highest mountain': 'Everest is the highest mountain above sea level.',
    'the largest desert': 'Antarctica is the largest desert, and the Sahara is the largest hot one.',
    'the largest country': 'Russia is the largest country by area.',
    'the smallest country': 'Vatican City is the smallest country.',
    'the largest planet': 'Jupiter is the largest planet.',
    'the closest star': 'The Sun is the closest star, and Proxima Centauri is the next nearest.',
    'the largest animal': 'The blue whale is the largest animal.',
    'the fastest animal': 'The peregrine falcon is the fastest animal when diving.',
    'the largest rainforest': 'The Amazon is the largest rainforest.',
    'the deepest ocean trench': 'The Mariana Trench is the deepest place in the ocean.',
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
    'attention': 'the mechanism that lets a model weigh which earlier tokens matter for the next one',
    'gradient descent': 'an optimiser that nudges the weights downhill along the gradient of the loss',
    'backpropagation': 'the rule for computing how every weight contributed to the error',
    'a loss function': 'the number a model tries to make smaller, measuring how wrong it is',
    'overfitting': 'when a model memorises the training data and does worse on anything new',
    'a token': 'a small chunk of text, roughly a word or piece of a word, that a model reads at once',
    'an embedding': 'a list of numbers standing in for a word, learned so similar words sit close together',
    'training data': 'the examples a model learns from, which bound what it can possibly know',
    'inference': 'running a trained model to get an answer, as opposed to training it',
    'a parameter': 'one of the learned numbers inside a model, adjusted during training',
    'version control': 'a system that records changes to files so you can review and undo them',
    'a merge conflict': 'what git reports when two branches changed the same lines and it cannot choose',
    'a unit test': 'a small automated check that one piece of code behaves the way you expect',
    'a pull request': 'a proposal to merge one branch into another, with room for review first',
    'a bug': 'behaviour that differs from what the program was meant to do',
    'refactoring': 'changing how code is written without changing what it does',
    'the cloud': 'someone else computers, rented by the hour instead of bought outright',
    'an operating system': 'the software layer that manages hardware, memory and running programs',
    'ram': 'fast temporary memory that holds what your computer is working on right now',
    'a cpu': 'the general purpose processor that executes most of your program instructions',
    'a gpu': 'a processor with thousands of small cores, very good at parallel maths',
    'a server': 'a computer whose job is answering requests from other computers',
    'encryption': 'scrambling data so that only someone with the right key can read it',
    'a hash function': 'a one way function that turns any input into a fixed size fingerprint',
    'latency': 'the delay between asking for something and getting the first part of the answer',
    'bandwidth': 'how much data a connection can carry per second once it gets going',
    'an ip address': 'the number that identifies a machine on a network',
    'a browser': 'a program that fetches web pages and renders them for you',
    'open source': 'software whose source code anyone may read, use and modify',
    'photosynthesis': 'how plants turn sunlight, water and carbon dioxide into sugar and oxygen',
    'gravity': 'the attraction between masses, which keeps the planets in orbit',
    'evolution': 'change in inherited traits across generations, driven by natural selection',
    'dna': 'the molecule carrying the genetic instructions for building an organism',
    'a cell': 'the smallest unit of life, and the building block of every organism',
    'an atom': 'the smallest piece of an element that still behaves like that element',
    'a molecule': 'two or more atoms bonded together',
    'an ecosystem': 'a community of living things together with the environment they depend on',
    'the water cycle': 'the loop of evaporation, condensation and rainfall that moves water around',
    'climate': 'the pattern of weather in a place averaged over many years',
    'a vaccine': 'a preparation that teaches the immune system to recognise a pathogen in advance',
    'inflation': 'a general rise in prices, so each unit of money buys a little less than before',
    'compound interest': 'interest earned on your interest, which is why savings grow faster over time',
    'supply and demand': 'the balance between how much of something exists and how much people want',
    'a budget': 'a plan for what your money will do before you spend it',
    'democracy': 'a system where power rests with the people, usually through elected representatives',
    'a constitution': 'the founding document setting out how a state is governed and what limits it',
    'philosophy': 'the study of fundamental questions about knowledge, reason, value and existence',
    'the scientific method': 'forming a hypothesis, testing it against evidence, and revising it',
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
    ('check the type of something',
     'type(value) tells you the type, and isinstance(value, int) checks against one you expect.'),
    ('make a dictionary in python',
     'Use braces with key and value pairs, like scores = {alice: 10, bob: 8}.'),
    ('add an item to a list',
     'items.append(x) adds one item, and items.extend(others) adds every item from another list.'),
    ('remove an item from a list',
     'items.remove(x) removes the first match, and items.pop(i) removes by index and returns it.'),
    ('slice a list',
     'items[1:4] takes elements one through three, and items[:3] takes the first three.'),
    ('check if a list is empty',
     'Just test it: if not items. An empty list is falsy in Python.'),
    ('write a comment in python',
     'Start the line with a hash. For a function, write a docstring in triple quotes instead.'),
    ('read a csv file',
     'Use the csv module: csv.DictReader gives you a dictionary per row, keyed by the header.'),
    ('parse json in python',
     'json.loads(text) turns a string into Python objects, and json.dumps(obj) goes the other way.'),
    ('run a python script',
     'Run python script.py from the terminal, in the directory that holds the file.'),
    ('find text in a string',
     'Use if needle in haystack, or haystack.find(needle) when you want the position.'),
    ('replace text in a string',
     'text.replace(old, new) returns a new string. Strings are immutable, so nothing changes in place.'),
    ('strip whitespace from a string',
     'text.strip() removes it from both ends, and there is lstrip and rstrip for one side.'),
    ('make a string lowercase',
     'text.lower() gives a lowercase copy, and text.upper() an uppercase one.'),
    ('sort a dictionary by value',
     'sorted(d.items(), key=lambda kv: kv[1]) sorts the pairs by value.'),
    ('zip two lists together',
     'zip(a, b) pairs them up, and you can loop over it directly or wrap it in list().'),
    ('write a function with a default argument',
     'Put the default in the signature, like def greet(name, greeting=Hello):.'),
    ('return more than one value',
     'Return a tuple: return first, second. The caller can unpack it into two names.'),
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
    'study for an exam': ['test yourself instead of rereading the notes',
                          'spread the sessions out rather than cramming them together',
                          'explain the hard parts out loud as if teaching someone'],
    'debug a hard problem': ['make it reproduce reliably before you try to fix it',
                             'cut the case down until almost nothing is left',
                             'check your assumptions one at a time, with evidence'],
    'read more': ['keep the book somewhere you already sit',
                  'allow yourself to abandon one you are not enjoying',
                  'read a little at the same time each day'],
    'cook better': ['salt as you go rather than only at the end',
                    'get the pan properly hot before anything goes in',
                    'taste at every stage and adjust while you still can'],
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
    ('do you have feelings', 'No. I produce text that can sound like it, but there is nothing behind it.'),
    ('can you browse the internet', 'I cannot search on my own. The app around me can run a web search and hand me the results.'),
    ('do you remember me', 'Only within this conversation. Once it is cleared, I start fresh.'),
    ('what is your context length', 'I read the last one hundred and twenty eight tokens of the conversation.'),
    ('what do you not know', 'A great deal. My corpus is small, so I am confident only about the topics I was trained on.'),
    ('can you make mistakes', 'Yes, often. I am a small model, so check anything that matters.'),
    ('what language are you written in', 'My whole network is written in Python with NumPy, including the backward pass.'),
    ('who made you', 'I was built as a from scratch project, tokenizer, transformer, training loop and all.'),
    ('how fast are you', 'Fast enough to stream a reply, because each token only costs one pass over the cache.'),
    ('what is your training data', 'A generated corpus of chat exchanges covering geography, arithmetic, Python, definitions and small talk.'),
    ('are you smart', 'Not very. I am a study model, and I am wrong about anything outside my corpus.'),
    ('why are you so small', 'So that I can be trained on a laptop processor and run in a browser tab.'),
    ('can you learn from me', 'No. My weights are fixed now; learning would mean another training run.'),
]

REFUSALS = [
    ('what is the weather today', 'I cannot check the weather myself. Turn on web search and I can be given a live answer.'),
    ('what time is it', 'I have no clock, so I cannot tell you the time.'),
    ('what is the news', 'I cannot read the news on my own. With web search on, the app can fetch it for me.'),
    ('what is the price of bitcoin', 'I cannot look up prices myself. Web search would have to fetch that for me.'),
    ('what year is it', 'I do not know the current date. Nothing in me tracks time.'),
    ('tell me about yesterday', 'I have no memory of any day. Every conversation starts from nothing.'),
    ('who won the game last night', 'I have no way to know. That is live information and my corpus is fixed.'),
]

SEARCH_GROUNDED = [
    ('search the web for me', 'Turn on web search and ask again, and I will answer from what it finds.'),
    ('can you look something up', 'With web search on, yes. The app fetches the page and gives me the text.'),
    ('how does your web search work', 'The app runs the search, then puts the results in front of me before I answer.'),
    ('where did you get that', 'From the search results the app gave me, not from my own training.'),
]

UNIT_FACTS = [
    ('how many centimetres are in a metre', 'There are 100 centimetres in a metre.'),
    ('how many millimetres are in a centimetre', 'There are 10 millimetres in a centimetre.'),
    ('how many metres are in a kilometre', 'There are 1000 metres in a kilometre.'),
    ('how many grams are in a kilogram', 'There are 1000 grams in a kilogram.'),
    ('how many millilitres are in a litre', 'There are 1000 millilitres in a litre.'),
    ('how many minutes are in an hour', 'There are 60 minutes in an hour.'),
    ('how many hours are in a day', 'There are 24 hours in a day.'),
    ('how many days are in a week', 'There are 7 days in a week.'),
    ('how many days are in a year', 'There are 365 days in a normal year and 366 in a leap year.'),
    ('how many weeks are in a year', 'There are 52 weeks in a year.'),
    ('how many months are in a year', 'There are 12 months in a year.'),
    ('how many seconds are in a minute', 'There are 60 seconds in a minute.'),
    ('how many sides does a triangle have', 'A triangle has 3 sides.'),
    ('how many sides does a square have', 'A square has 4 sides.'),
    ('how many sides does a hexagon have', 'A hexagon has 6 sides.'),
    ('how many sides does an octagon have', 'An octagon has 8 sides.'),
    ('how many degrees are in a circle', 'There are 360 degrees in a circle.'),
    ('how many degrees are in a triangle', 'The angles of a triangle add up to 180 degrees.'),
    ('how many continents are there', 'There are 7 continents.'),
    ('how many oceans are there', 'There are 5 oceans.'),
    ('how many planets are in the solar system', 'There are 8 planets in the solar system.'),
    ('how many letters are in the alphabet', 'There are 26 letters in the English alphabet.'),
    ('how many colours are in a rainbow', 'A rainbow is usually described as having 7 colours.'),
    ('what is the boiling point of water', 'Water boils at 100 degrees celsius at sea level.'),
    ('what is the freezing point of water', 'Water freezes at 0 degrees celsius.'),
    ('how many bones are in the human body', 'An adult has 206 bones.'),
    ('how many players are on a football team', 'A football team has 11 players on the pitch.'),
]

SEQUENCES = {
    'day': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    'month': ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December'],
    'season': ['spring', 'summer', 'autumn', 'winter'],
}

OPPOSITES = {
    'hot': 'cold', 'big': 'small', 'fast': 'slow', 'up': 'down', 'day': 'night',
    'open': 'closed', 'happy': 'sad', 'light': 'dark', 'early': 'late',
    'hard': 'soft', 'wet': 'dry', 'full': 'empty', 'near': 'far', 'true': 'false',
    'young': 'old', 'rich': 'poor', 'strong': 'weak', 'clean': 'dirty',
}

CATEGORIES = {
    'a dog': 'an animal', 'a cat': 'an animal', 'an eagle': 'a bird',
    'a salmon': 'a fish', 'an oak': 'a tree', 'a rose': 'a flower',
    'an apple': 'a fruit', 'a carrot': 'a vegetable', 'copper': 'a metal',
    'granite': 'a rock', 'python': 'a programming language', 'the violin': 'an instrument',
    'a whale': 'a mammal', 'a frog': 'an amphibian', 'a snake': 'a reptile',
}

NUMBER_WORDS = {
    2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
    9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve', 13: 'thirteen',
    14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen',
    18: 'eighteen', 19: 'nineteen', 20: 'twenty',
}

SMALLTALK = [
    (['hi', 'hello', 'hey', 'good morning', 'good evening', 'good afternoon'],
     ['Hello. What would you like to talk about?', 'Hi there. How can I help?',
      'Hey. What are you working on?', 'Hello. Ask me anything.']),
    (['thanks', 'thank you', 'thanks a lot', 'cheers', 'much appreciated'],
     ['You are welcome.', 'Happy to help.', 'Any time.', 'Glad that helped.']),
    (['bye', 'goodbye', 'see you', 'good night'],
     ['Goodbye.', 'See you around.', 'Take care.']),
    (['how are you', 'how are you doing', 'how is it going'],
     ['I am running fine, thank you. What can I do for you?',
      'Good, and ready to help. What is on your mind?']),
    (['sorry', 'my mistake', 'my bad'],
     ['No problem at all.', 'That is completely fine.']),
    (['ok', 'okay', 'got it', 'i see', 'makes sense'],
     ['Anything else you want to look at?', 'Let me know what is next.']),
    (['nice', 'cool', 'great', 'awesome'],
     ['Glad you think so.', 'Happy to hear it.']),
    (['help', 'i need help', 'can you help me'],
     ['Of course. What are you stuck on?', 'Tell me the problem and I will try.']),
    (['what should i ask you', 'what can i ask'],
     ['Try a capital city, a small sum, a Python question, or ask what I am.']),
]

FOLLOW_UPS = [
    ('thanks', ['You are welcome.', 'Happy to help.', 'Any time.']),
    ('can you say more', ['That is about as far as my knowledge goes on this one.',
                          'I am a small model, so that is the short version.']),
    ('are you sure', ['Reasonably sure, but I am small enough that you should check anything important.',
                      'That is what I learned, though I can be wrong.']),
    ('why', ['Because that is what my training data consistently said about it.']),
    ('and', ['That is all I have on it.']),
    ('really', ['That is what I was trained on, yes.']),
]


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def _dialogue(turns: list[tuple[str, str]]) -> str:
    parts = []
    for user, assistant in turns:
        parts.append(f'{USER} {user} {ASSISTANT} {assistant} {END}')
    return ' '.join(parts)


def geography(rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for country, capital in CAPITALS.items():
        for q in (f'what is the capital of {country}',
                  f'capital of {country}',
                  f'whats the capital city of {country}',
                  f'tell me the capital of {country}',
                  f'which city is the capital of {country}'):
            # Keep the country in most answers: the association is the thing
            # this model finds hardest, so the corpus states it plainly.
            out.append((q, rng.choice([
                f'The capital of {country} is {capital}.',
                f'The capital of {country} is {capital}.',
                f'{capital} is the capital of {country}.',
                f'It is {capital}.',
            ])))
        out.append((f'what country is {capital} the capital of',
                    f'{capital} is the capital of {country}.'))
    for country, language in LANGUAGES.items():
        out.append((f'what language do they speak in {country}',
                    f'The main language of {country} is {language}.'))
        out.append((f'what is spoken in {country}', f'Mostly {language}.'))
        out.append((f'what language is spoken in {country}',
                    f'They mainly speak {language} in {country}.'))
    for country, continent in CONTINENTS.items():
        out.append((f'what continent is {country} in', f'{country} is in {continent}.'))
        out.append((f'where is {country}', f'{country} is in {continent}.'))
    for country, currency in CURRENCIES.items():
        out.append((f'what currency does {country} use', f'{country} uses {currency}.'))
        out.append((f'what money do they use in {country}', f'They use {currency}.'))
    return out


def science(rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for planet, description in PLANETS.items():
        out.append((f'tell me about {planet}', f'{planet} is {description}.'))
        out.append((f'what is {planet}', f'{planet} is {description}.'))
    for name, (symbol, number) in ELEMENTS.items():
        out.append((f'what is the symbol for {name}', f'The symbol for {name} is {symbol}.'))
        out.append((f'what is the chemical symbol of {name}', f'It is {symbol}.'))
        out.append((f'what element is {symbol}', f'{symbol} is {name}.'))
        if number <= 20:
            out.append((f'what is the atomic number of {name}',
                        f'The atomic number of {name} is {number}.'))
    for topic, fact in SUPERLATIVES.items():
        out.append((f'what is {topic}', fact))
        out.append((f'whats {topic} in the world', fact))
    return out


def arithmetic(rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for _ in range(500):
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
    for n in range(2, 21):
        out.append((f'what is the square of {n}', f'{n} squared is {n * n}.'))
        out.append((f'is {n} even or odd', f'{n} is {"even" if n % 2 == 0 else "odd"}.'))
        out.append((f'how do you spell the number {n}', f'You spell it {NUMBER_WORDS[n]}.'))
        out.append((f'what is double {n}', f'Double {n} is {n * 2}.'))
        if n % 2 == 0:
            out.append((f'what is half of {n}', f'Half of {n} is {n // 2}.'))
    for n in (10, 20, 25, 40, 50, 60, 80, 100, 200):
        out.append((f'what is 10 percent of {n}', f'10 percent of {n} is {n // 10}.'))
        out.append((f'what is 50 percent of {n}', f'50 percent of {n} is {n // 2}.'))
    for n in (2, 3, 5, 7, 11, 13, 17, 19):
        out.append((f'is {n} a prime number', f'Yes, {n} is a prime number.'))
    for n in (4, 6, 8, 9, 10, 12, 15):
        out.append((f'is {n} a prime number',
                    f'No, {n} is not prime because it divides evenly by smaller numbers.'))
    return out


def language_and_logic(rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for kind, items in SEQUENCES.items():
        for i, item in enumerate(items):
            nxt = items[(i + 1) % len(items)]
            prev = items[(i - 1) % len(items)]
            out.append((f'what {kind} comes after {item}', f'{nxt} comes after {item}.'))
            out.append((f'what {kind} comes before {item}', f'{prev} comes before {item}.'))
        out.append((f'how many {kind}s are there', f'There are {len(items)}.'))
        out.append((f'name the {kind}s', 'They are ' + ', '.join(items[:-1]) + f' and {items[-1]}.'))
    for word, opposite in OPPOSITES.items():
        out.append((f'what is the opposite of {word}', f'The opposite of {word} is {opposite}.'))
        out.append((f'whats the opposite of {opposite}', f'It is {word}.'))
    for thing, category in CATEGORIES.items():
        out.append((f'is {thing} {category}', f'Yes, {thing} is {category}.'))
        out.append((f'what is {thing}', f'{thing.capitalize()} is {category}.'))
    return out


def knowledge(rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for term, meaning in DEFINITIONS.items():
        for q in (f'what is {term}', f'explain {term}', f'what does {term} mean',
                  f'can you explain {term} to me', f'define {term}'):
            out.append((q, rng.choice([
                f'{term.capitalize()} is {meaning}.',
                f'It is {meaning}.',
            ])))
    for task, ans in PYTHON_QA:
        for q in (f'how do i {task}', f'how to {task}', f'whats the best way to {task}',
                  f'can you show me how to {task}'):
            out.append((q, ans))
    for topic, tips in ADVICE.items():
        answer = (f'Three things help most. First, {tips[0]}. Second, {tips[1]}. '
                  f'Third, {tips[2]}.')
        for q in (f'how do i {topic}', f'any tips to {topic}', f'help me {topic}',
                  f'whats the best way to {topic}'):
            out.append((q, answer))
    return out


def conversation(rng: random.Random) -> list[tuple[str, str]]:
    out = list(PERSONA) + list(REFUSALS) + list(SEARCH_GROUNDED) + list(UNIT_FACTS)
    for prompts, replies in SMALLTALK:
        for prompt in prompts:
            out.append((prompt, rng.choice(replies)))
    return out


# Associative recall (a country to its capital, an element to its symbol) is
# what a model this small struggles with most, so those categories are drawn
# more often than the ones it picks up quickly.
WEIGHTS = [
    (geography, 4),
    (knowledge, 3),
    (arithmetic, 2),
    (science, 2),
    (language_and_logic, 2),
    (conversation, 2),
]


def build(seed: int = 7, n_dialogues: int = 30000) -> str:
    """Return the full corpus text."""
    rng = random.Random(seed)
    pool: list[tuple[str, str]] = []
    for fn, weight in WEIGHTS:
        pairs = fn(rng)
        pool.extend(pairs * weight)
    rng.shuffle(pool)

    lines: list[str] = []
    for _ in range(n_dialogues):
        n_turns = rng.choices([1, 2, 3], weights=[5, 3, 2])[0]
        turns = [rng.choice(pool) for _ in range(n_turns)]
        # Sometimes end on a short follow-up, so the model learns to keep the
        # thread going instead of only answering cold questions.
        if rng.random() < 0.15:
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
    tokens = split(text)
    print(f'wrote {out} — {len(text):,} chars, {len(tokens):,} tokens, '
          f'{len(set(tokens)):,} distinct')


if __name__ == '__main__':
    main()
