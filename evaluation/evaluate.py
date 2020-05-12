import csv
import collections.abc
import io
import json
import sys
import statistics
import subprocess
import warnings
from tabulate import tabulate
import yaml
from rdflib import URIRef

from db.graph import Configuration
from utils.graph import RDF, OTD, DCAT, SKOS
from otd.constants import SIMTYPE_SIMILARITY, SIMTYPE_AUTOTAG, simtypes
from utils.common_cli import float_between_0_and_1
from ontosearch.search import get_configurations_from_doc


def parse_file(filename):
    if filename == '-':
        in_document = io.StringIO()
        in_document.write(sys.stdin.read())
        file_contents = in_document.getvalue()
        document = yaml.load(file_contents)
    else:
        with open(filename) as fp:
            file_contents = None
            document = yaml.load(fp)

    try:
        queries = document['query']
    except KeyError as e:
        raise RuntimeError(
            "Please specify the key 'query' in the given YAML document"
        ) from e
    except TypeError as e:
        if document is None:
            raise RuntimeError(
                'Please provide a non-empty YAML document'
            ) from e
        else:
            raise RuntimeError(
                'Please ensure the YAML document has a mapping at the top level'
            ) from e

    if not isinstance(queries, collections.abc.Mapping):
        raise RuntimeError(
            "'query' must be a mapping between queries and relevant concepts "
            "and datasets"
        )

    if not all(
            map(
                lambda q: isinstance(q, list),
                queries.values()
            )
    ):
        raise RuntimeError(
            "Please ensure all values in the 'query' mapping are lists of "
            "datasets and concepts related to that query"
        )

    ground_truth = document.get('ground-truth', dict())

    ground_simtype = ground_truth.get('simtype', SIMTYPE_SIMILARITY)
    if ground_simtype not in simtypes:
        raise RuntimeError(
            f'Ground truth simtype "{ground_simtype}" was not recognized'
        )

    ground_threshold = ground_truth.get('threshold', 0.8)
    ground_threshold = float_between_0_and_1(ground_threshold)

    metadata = document.get('metadata', {})
    if not isinstance(metadata, collections.abc.Mapping):
        raise RuntimeError(f"'metadata' must be a mapping, but got {metadata}")

    # Normally we get configuration from metadata, but fetch it for
    # --print-relevant
    configurations = get_configurations_from_doc(document)

    return {
        'queries': queries,
        'ground_simtype': ground_simtype,
        'ground_threshold': ground_threshold,
        'filename': filename,
        'file_contents': file_contents,
        'configurations': configurations,
        'metadata': metadata,
    }


def evaluate(
        queries,
        ground_simtype,
        ground_threshold,
        filename,
        file_contents,
        metadata,
        **_
):
    command = [
        sys.executable or 'python',
        sys.argv[0],
        'multisearch',
        filename,
    ]

    input_text = None
    if file_contents is not None:
        input_text = file_contents

    process_info = subprocess.run(
        command,
        universal_newlines=True,
        input=input_text,
        stdout=subprocess.PIPE,
        check=True,
    )
    return evaluate_output(
        process_info.stdout,
        metadata,
        queries,
        ground_simtype,
        ground_threshold,
    )


def evaluate_output(
        output,
        metadata,
        queries,
        ground_simtype,
        ground_threshold,
        **_
):
    results = output.split('\n\n')
    results = map(lambda s: s.strip().split('\n'), results)
    results = filter(None, map(
        lambda lines: process_results(
            lines,
            metadata,
            queries,
            ground_simtype,
            ground_threshold
        ),
        results
    ))
    return tuple(results)


def process_results(
        lines,
        base_metadata,
        queries,
        ground_simtype,
        ground_threshold,
):
    # We base our metadata on the base_metadata
    metadata = base_metadata.copy()
    # Then we override with data from multisearch
    ext_metadata = json.loads(lines[0])
    metadata.update(ext_metadata)

    matching_datasets = lines[1:]

    query = metadata['query']
    configuration = metadata['configuration']
    if query not in queries:
        warnings.warn(
            f'The query "{query}" was not found in the YAML file, skipping…'
        )
        return None

    raw_relevant_datasets = queries[query]
    relevant_datasets = find_relevant_datasets(
        raw_relevant_datasets,
        configuration,
        ground_simtype,
        ground_threshold
    )

    metrics = calculate_metrics(matching_datasets, relevant_datasets)

    # Return combination of the metadata for the query, and calculated metrics
    metadata.update(metrics)
    return metadata


def print_relevant(
        queries,
        ground_simtype,
        ground_threshold,
        configurations,
        **_
):
    multiple_configs = len(configurations) > 1

    for query, relevant_spec in queries.items():
        for config in configurations:
            if multiple_configs:
                print(f'Query: "{query}". Configuration: "{config}"')
            else:
                print(f'Query: "{query}"')
            relevant_datasets = find_relevant_datasets(
                relevant_spec,
                config,
                ground_simtype,
                ground_threshold,
            )
            for dataset in relevant_datasets:
                print(dataset)
            if not relevant_datasets:
                print('No datasets were found.')
            # Separate queries/configs with blank line
            print()


def find_relevant_datasets(relevant_spec, configuration, simtype, threshold):
    # Load necessary graphs
    config = Configuration.from_uuid(configuration)
    dataset_graph = config.get_dataset().graph
    ontology_graph = config.get_ontology().graph
    if simtype == SIMTYPE_SIMILARITY:
        similarity_graph = config.get_similarity().graph
    elif simtype == SIMTYPE_AUTOTAG:
        similarity_graph = config.get_autotag().graph
    else:
        raise ValueError(f'Simtype {simtype} not supported')

    # We will be creating a list of relevant datasets
    relevant_datasets = set()

    # Go through all relevant datasets/concepts named in the YAML file
    for spec in relevant_spec:
        # Check for concepts joined with AND
        if isinstance(spec, collections.abc.Mapping):
            raw_concepts = spec.get('and', spec.get('AND'))
            if not raw_concepts:
                raise ValueError(
                    f'Did not understand {spec}, expected mapping to have key '
                    f'named "and" or "AND" with list of concepts.'
                )

            # This is an intersection of concepts!
            # We keep a list of datasets that matched so far
            matching_datasets = None

            for concept in raw_concepts:
                # This is a concept, right?
                concept = URIRef(concept)
                if (concept, RDF.type, SKOS.Concept) not in ontology_graph:
                    raise ValueError(
                        f'Did not recognize {concept} as a concept for '
                        f'configuration {configuration}'
                    )

                # What datasets are associated with this concept?
                datasets = find_datasets_from_concept(
                    concept,
                    similarity_graph,
                    threshold
                )
                datasets = set(datasets)

                # Update our list of matching datasets
                if matching_datasets is None:
                    # First iteration, keep all datasets
                    matching_datasets = datasets
                else:
                    # Not first iteration, filter out any datasets not tagged
                    # with this concept
                    matching_datasets.intersection_update(datasets)

            # Warn if we didn't actually match with any concepts (likely a
            # mistake)
            if not matching_datasets:
                warnings.warn(f'No dataset matched with all of the concepts '
                              f'{raw_concepts}')
            # Now that we have the result of the intersection, we can add it to
            # the list
            relevant_datasets.update(matching_datasets)
            # Skip the processing below
            continue

        # We are assuming concepts or datasets are RDF URIs
        spec = URIRef(spec)
        # Are we dealing with a dataset or concept?
        if (spec, RDF.type, DCAT.Dataset) in dataset_graph:
            # We are naming a relevant dataset, simply add it
            relevant_datasets.add(str(spec))
        elif (spec, RDF.type, SKOS.Concept) in ontology_graph:
            # We are naming a relevant concept, add all datasets connected to it
            relevant_datasets.update(
                find_datasets_from_concept(spec, similarity_graph, threshold)
            )
        else:
            raise ValueError(
                f'Did not recognize {spec} as a concept or dataset for '
                f'configuration {configuration}'
            )
    return relevant_datasets


def find_datasets_from_concept(concept, similarity_graph, threshold):
    relevant_datasets = []
    # Start with navigating dataset taggings related to this concept
    similarities = similarity_graph.subjects(OTD.concept, concept)

    for sim in similarities:
        # What is the similarity score for this dataset-concept tag?
        score = similarity_graph.value(sim, OTD.score, None)

        # Is it above our threshold?
        if float(score) < threshold:
            # Nope, skip
            continue

        # Add this dataset
        dataset = similarity_graph.value(sim, OTD.dataset, None)
        relevant_datasets.append(str(dataset))
    return relevant_datasets


def calculate_metrics(matching_datasets, relevant_datasets):
    # Create array with relevant/irrelevant for each retrieved dataset
    result_relevance = tuple(
        map(
            lambda r: r in relevant_datasets,
            matching_datasets
        )
    )
    num_fetched = len(matching_datasets)
    num_relevant_existing = len(relevant_datasets)
    num_relevant_fetched = num_true(result_relevance)
    num_r_relevant_fetched = num_true(result_relevance[:num_relevant_existing])

    try:
        precision = num_relevant_fetched / num_fetched
    except ZeroDivisionError:
        warnings.warn('For at least one query, not a single dataset was '
                      'fetched')
        precision = 0.0

    try:
        recall = num_relevant_fetched / num_relevant_existing
        r_precision = num_r_relevant_fetched / num_relevant_existing
        avg_precision = calculate_avg_precision(
            result_relevance,
            num_relevant_existing
        )
    except ZeroDivisionError:
        warnings.warn('For at least one query, there are no relevant datasets '
                      'defined')
        recall = 0.0
        r_precision = 0.0
        avg_precision = 0.0

    try:
        f1_measure = (2 * precision * recall) / (precision + recall)
    except ZeroDivisionError:
        f1_measure = 0.0

    return {
        'fetched': num_fetched,
        'relevant': num_relevant_existing,
        'relevant & fetched': num_relevant_fetched,
        'precision': precision,
        'recall': recall,
        'f1-measure': f1_measure,
        'r-precision': r_precision,
        'avg precision': avg_precision,
    }


def num_true(iterable):
    return len(
        tuple(
            filter(
                None,
                iterable
            )
        )
    )


def calculate_avg_precision(result_relevance, num_relevant_existing):
    precision_scores = []
    for position, is_relevant in enumerate(result_relevance):
        if not is_relevant:
            continue

        # What is the precision at this point?
        num_so_far = position + 1
        sub_result = result_relevance[:num_so_far]
        num_relevant_so_far = num_true(sub_result)
        precision = num_relevant_so_far / num_so_far
        precision_scores.append(precision)

    # Any relevant dataset not retrieved counts as precision = 0.0
    num_relevant_not_fetched = num_relevant_existing - len(precision_scores)
    not_fetched_scores = [0.0] * num_relevant_not_fetched
    precision_scores.extend(not_fetched_scores)

    return statistics.mean(precision_scores)


def print_results(results, table_format='psql', destination=None):
    if destination is None:
        destination = sys.stdout

    if table_format.lower() == 'csv':
        output = format_as_csv(results)
    else:
        output = format_using_tabulate(results, table_format)
    print(output, file=destination)


def format_as_csv(results):
    stream = io.StringIO(newline='')
    csv_writer = csv.DictWriter(stream, fieldnames=results[0].keys())
    csv_writer.writeheader()

    for r in results:
        csv_writer.writerow(r)
    return stream.getvalue().strip()


def format_using_tabulate(results, table_format):
    return tabulate(
        results,
        headers='keys',
        tablefmt=table_format,
    )
