from collections import namedtuple
import logging

from yatetradki.sites.slovari import YandexSlovari
from yatetradki.sites.thesaurus import Thesaurus
from yatetradki.sites.freedict import TheFreeDictionary
from yatetradki.sites.bnc import BncSimpleSearch

from yatetradki.pretty import Prettifier
from yatetradki.cache import Cache
from yatetradki.utils import load_colorscheme
from yatetradki.utils import get_terminal_width_fallback
from yatetradki.utils import load_credentials_from_netrc


_logger = logging.getLogger()


COOKIE_JAR = 'cookiejar.dat'
NETRC_HOST = 'YandexSlovari'


CachedWord = namedtuple('CachedWord',
                        'tetradki_word thesaurus_word '
                        'freedict_word bnc_word')


def fetch(args):
    if None in (args.login, args.password):
        login, password = load_credentials_from_netrc(NETRC_HOST)
        if None in (login, password):
            _logger.error('Please specify login and password')
            return 1
        args.login, args.password = login, password

    cache = Cache(args.cache)

    slovari = YandexSlovari(args.login, args.password, COOKIE_JAR)
    words = slovari.get_words()
    words = words[:args.num_words] if args.num_words else words

    thesaurus = Thesaurus()
    freedict = TheFreeDictionary()
    bnc = BncSimpleSearch()

    cache.order = [x.wordfrom for x in words]
    words_fetched = 0
    for i, word in enumerate(words):
        if not cache.contains(word.wordfrom):
            _logger.info(u'Fetching {0}/{1}: {2}'
                         .format(i + 1, len(words), word.wordfrom))
            thesaurus_word = thesaurus.find(word.wordfrom)
            freedict_word = freedict.find(word.wordfrom)
            bnc_word = bnc.find(word.wordfrom)
            cache.save(word.wordfrom, CachedWord(word,
                                                 thesaurus_word,
                                                 freedict_word,
                                                 bnc_word))
            words_fetched += 1
            cache.flush() # save early

    if words_fetched:
        _logger.info('{0} new words fetched'.format(words_fetched))


def _add_numbers(text):
    lines = text.splitlines()
    lines = [u'{0:03} {1}'.format(i + 1, line) for i, line in enumerate(lines)]
    return u'\n'.join(lines)


def _show_words(args, cache, words):
    prettifier = Prettifier(load_colorscheme(args.colors),
                            get_terminal_width_fallback(args.width),
                            args.height, args.num_columns, args.delim)

    cached_words = filter(None, map(cache.load, words))
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

    cache = Cache(args.cache)
    words = cache.order
    words = words[:args.num_words] if args.num_words else words
    _show_words(args, cache, words)


def words(args):
    cache = Cache(args.cache)
    words = cache.order
    cached_words = filter(None, map(cache.load, words))
    result = u'\n'.join([x.tetradki_word.wordfrom for x in cached_words])
    print(result.encode('utf-8'))


def word(args):
    cache = Cache(args.cache)
    _show_words(args, cache, args.words)
