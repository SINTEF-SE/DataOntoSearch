import logging
from requests_html import HTMLSession
from utils.graph import prepare_query, query
import rdflib

logger = logging.getLogger(__name__)


class GoogleDatasetSearch:
    """
    Tool for performing automated queries against Google Dataset Search.
    """
    URL_BASE = 'https://toolbox.google.com/datasetsearch/search'
    DATASET_LOOKUP_Q = prepare_query('''
        SELECT ?dataset
        WHERE {
            ?dataset a         dcat:Dataset ;
                     dct:title ?actualTitle .
            # Restrict to datasets with a matching title. Since Google cuts off
            # the title, we must search for datasets that start the same way.
            FILTER (
                STRSTARTS (
                    ?actualTitle,
                    ?title
                )
            ) 
        }
    ''')
    DATASET_LOOKUP_Q_EXACT = prepare_query('''
        SELECT ?dataset
        WHERE {
            ?dataset a         dcat:Dataset ;
                     dct:title ?title .
        }
    ''')

    def __init__(self, dataset):
        self.session = HTMLSession()
        self.dataset = dataset

    def search(self, query, site=None):
        if not query:
            return []

        logger.info(f'Performing query "{query}"')
        r = self._get_request(query, site)
        titles = self._extract_titles(r)
        datasets = self._find_dataset_for_titles(titles)
        return self._filter_datasets(datasets)

    def _get_request(self, query, site):
        if site:
            query = f'site:{site} {query}'

        r = self.session.get(self.URL_BASE, params={'query': query})
        r.raise_for_status()
        return r

    @staticmethod
    def _extract_titles(r):
        # Let the web page do its client-side rendering
        r.html.render()
        # Now we can find the rendered titles
        headings = r.html.find('ol > li h1')
        return [el.text for el in headings]

    def _find_dataset_for_titles(self, titles):
        return [self._find_dataset_for_title(t) for t in titles]

    def _find_dataset_for_title(self, title: str):
        # Remove trailing ellipsis (since Google cuts off the title)
        is_exact = True
        if title.endswith('.'):
            title = title.rstrip('.')
            is_exact = False
        # Do the query
        title_literal = rdflib.Literal(title)
        res = query(
            self.dataset.graph,
            self.DATASET_LOOKUP_Q_EXACT if is_exact else self.DATASET_LOOKUP_Q,
            title=title_literal,
        )

        # Instead of looping with a for-loop, simply get the first result
        try:
            first_match = next(iter(res))
            return str(first_match['dataset'])
        except StopIteration:
            logger.warning(f'Unable to find dataset with title "{title}"')
            return None

    @staticmethod
    def _filter_datasets(datasets):
        # Simply remove unrecognized datasets from the results. Their presence
        # might bias Google results one way or another, depending on if you say
        # they are relevant or not. By removing them, we are essentially asking
        # ourselves, "what would Google return, had they been constrained to the
        # the same datasets as DataOntoSearch?", which should be fair.
        return [d for d in datasets if d is not None]
