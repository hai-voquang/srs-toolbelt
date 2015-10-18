# encoding=utf8
import logging
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock

from yatetradki.sites.slovari import YandexTetradki
from yatetradki.sites.slovari import YandexSlovari
from yatetradki.sites.thesaurus import Thesaurus
from yatetradki.sites.freedict import TheFreeDictionary
from yatetradki.sites.bnc import BncSimpleSearch

from yatetradki.pretty import Prettifier
# from yatetradki.cache import PickleCache
from yatetradki.cache import EvalReprTsvCache
from yatetradki.utils import load_colorscheme
from yatetradki.utils import get_terminal_width_fallback
from yatetradki.utils import load_credentials_from_netrc
from yatetradki.types import CachedWord


_logger = logging.getLogger()


COOKIE_JAR = 'cookiejar.dat'
NETRC_HOST = 'YandexTetradki'
LIMIT = 2
BR = u'<br>'
BR_EXAMPLES = u' :: '


def _limit(list_):
    return list_[:LIMIT]


class AnkiFormatter(object):
    """
    Export SlovariWord into anki format. Supports both directions: en->ru,
    ru->en. Add part of speech, transcription, translation and usage examples.
    """
    def __init__(self, word):
        self._word = word

    def _examples(self, examples, front):
        return [u'syn: {0}'.format(example.synonyms)
                if example.synonyms
                else u'{0}'.format(example.examplefrom if front
                                   else example.exampleto)
                for example in examples]

    def _entries(self, entries, front):
        back_newline = '' if front else BR
        return [u'{0}{1}{2}'.format(
            '' if front else '= ' + entry.wordto,
            back_newline + BR_EXAMPLES.join(self._examples(_limit(entry.examples), front)),
            BR)
            for entry in entries]

    def _groups(self, groups, front):
        return [u'({0}){1}{2}'.format(
            group.part_of_speech,
            BR,
            BR.join(self._entries(_limit(group.entries), front)))
            for group in groups]

    def __call__(self):
        groups = _limit(self._word.groups)
        transcription = self._word.transcription
        front = u'{0}{1}{2}{3}'.format(
            self._word.wordfrom.decode('utf8'),
            ' ' + transcription if transcription else '',
            BR,
            BR.join(self._groups(groups, front=True)))
        back = BR.join(self._groups(groups, front=False))
        return u'{0}\t{1}'.format(front, back)


def fetch_word(args):
    # cmd = Commander(args)
    for word in args.words:
        # print(word)
        slovari = YandexSlovari()
        data = slovari.find(word)
        anki = AnkiFormatter(data)
        print(anki().encode('utf8'))


#
# # XXX: rename me later
# class Commander(object):
#     def __init__(self, args):
#         self._args = args
#
#         self._thesaurus = Thesaurus()
#         self._freedict = TheFreeDictionary()
#         self._bnc = BncSimpleSearch()
#
#     def fetch_words(self, words):
#         thesaurus_word = thesaurus.find(word.wordfrom)
#         freedict_word = freedict.find(word.wordfrom)
#         bnc_word = bnc.find(word.wordfrom)
#

def fetch(args):
    if None in (args.login, args.password):
        login, password = load_credentials_from_netrc(NETRC_HOST)
        if None in (login, password):
            _logger.error('Please specify login and password')
            return 1
        args.login, args.password = login, password

    # cache = PickleCache(args.cache)
    cache = EvalReprTsvCache(args.cache)

    slovari = YandexTetradki(args.login, args.password, COOKIE_JAR)
    words = slovari.newest(args.num_words)
    #words = slovari.get_words()
    #words = words[:args.num_words] if args.num_words else words
    # print('yandex words', words)

    thesaurus = Thesaurus()
    freedict = TheFreeDictionary()
    bnc = BncSimpleSearch()
    slovari = YandexSlovari()
    # data = slovari.find(word)

    # order = [x.wordfrom for x in words]
    #cache.order = [x.wordfrom for x in words]
    # print(cache.order)
    # print(order)
    words_fetched = [0]

    cache_lock = Lock()

    # def process_word(pair(i, word)):
    def process_word(pair):
        i, word = pair
        # TODO: deal with this ugly locks
        with cache_lock:
            if cache.contains(word.wordfrom):
                return

        _logger.info(u'Fetching {0}/{1}: {2}'
                     .format(i + 1, len(words), word.wordfrom))
        try:
            slovari_word = slovari.find(word.wordfrom)
            thesaurus_word = thesaurus.find(word.wordfrom)
            freedict_word = freedict.find(word.wordfrom)
            bnc_word = bnc.find(word.wordfrom)
        except Exception:
            _logger.exception(u'Could not fetch word {0}'
                              .format(word.wordfrom))
        else:
            with cache_lock:
                cache.put(word.wordfrom,
                          CachedWord(word, slovari_word, thesaurus_word,
                                     freedict_word, bnc_word))
                words_fetched[0] += 1
                cache.flush() # save early
            _logger.info(u'Fetched {0}'.format(word.wordfrom))

    if args.jobs > 1:
        pool = ThreadPool(args.jobs)
        pool.map(process_word, enumerate(words))
        pool.close()
        pool.join()
    else:
        map(process_word, enumerate(words))

    if words_fetched[0]:
        _logger.info('{0} new words fetched'.format(words_fetched[0]))


def export(args):
    # cache = PickleCache(args.cache)
    cache = EvalReprTsvCache(args.cache)
    words = cache.newest(args.num_words)
    #words = cache.order
    #words = words[:args.num_words] if args.num_words else words
    _export_words(args, cache, words)


def _anki(word):
    string = AnkiFormatter(word.slovari_word)()
    return u'\n{0}'.format(string).encode('utf8')


def _export_words(args, cache, words):
    cached_words = filter(None, map(cache.get, words))
    if args.anki_card:
        # anki = AnkiFormatter(data)
        # print(anki().encode('utf8'))

        with open(args.anki_card, 'w') as output:
            output.writelines(_anki(word) for word in cached_words)
            # output.writelines(
            #     u'{0}\t{1}\n'.format(word.tetradki_word.wordfrom,
            #                          ', '.join(word.tetradki_word.wordsto))
            #     .encode('utf-8')
            #     for word in cached_words)
        print('Exported {0} words into file {1}'.format(len(cached_words),
                                                        args.anki_card))


def _add_numbers(text):
    lines = text.splitlines()
    lines = [u'{0:03} {1}'.format(i + 1, line) for i, line in enumerate(lines)]
    return u'\n'.join(lines)


def _show_words(args, cache, words):
    prettifier = Prettifier(load_colorscheme(args.colors),
                            get_terminal_width_fallback(args.width),
                            args.height, args.num_columns, args.delim)

    cached_words = filter(None, map(cache.get, words))
    result = prettifier(cached_words)
    if args.numbers:
        result = _add_numbers(result)
    print(result.encode('utf-8'))

    words_missing = len(words) - len(cached_words)
    if words_missing:
        _logger.error('Could not load {0} words from cache'.format(words_missing))


def show(args):
    if args.num_columns:
        args.num_words = 0

    # cache = PickleCache(args.cache)
    cache = EvalReprTsvCache(args.cache)
    words = cache.newest(args.num_words)
    # words = cache.order
    # words = words[:args.num_words] if args.num_words else words
    _show_words(args, cache, words)


def words(args):
    # cache = PickleCache(args.cache)
    cache = EvalReprTsvCache(args.cache)
    words = cache.order
    cached_words = filter(None, map(cache.get, words))
    result = u'\n'.join([x.tetradki_word.wordfrom for x in cached_words])
    print(result.encode('utf-8'))


def word(args):
    # cache = PickleCache(args.cache)
    cache = EvalReprTsvCache(args.cache)
    _show_words(args, cache, args.words)
