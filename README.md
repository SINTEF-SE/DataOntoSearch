# DataOntoSearch
Ontology Based Semantic Search for Open Transport Data 

This repository contains source-code and stubs of code used in the development
of the prototype **DataOntoSearch**. Its purpose is to help developers find
the datasets they want to use, by not requiring them to use the exact same words
in their search queries as those used by the dataset publishers.


## Preparing

**Reading this guide**: Any Python commands in the instructions assume you
already have the virtual environment loaded. Using Pip and Virtualenv, you do this by
sourcing the `activate` inside the virtual environment folder. For example, if
the virtual environment folder is called `venv`, you run `. venv/bin/activate`.

1. (Fork and) clone this repository, so you have a copy locally
2. While in this directory, set up the Python virtual environment and install from `requirements.txt`. See the guide at https://docs.python-guide.org/dev/virtualenvs/#lower-level-virtualenv for how to use Virtualenv and Pip.
4. Follow the link in `ordvev/README.md` and extract the files into the `ordvev/` directory
5. Install and configure MongoDB so you have a user (with password) which can access it. You will also need to enable authentication. See for example the [official guide from MongoDB](https://docs.mongodb.com/manual/tutorial/enable-authentication/).
6. Create a file called `.env` in this directory, where you define the variables:
   * `DB_USERNAME`: Username to use when logging in to MongoDB
   * `DB_PASSWD`: Password to use when logging in to MongoDB
   * `DB_HOST`: Name of server where MongoDB runs. Defaults to localhost
   * `DB_NAME`: Name of database to use in MongoDB. Defaults to ontodb
   
   To define for example `DB_USERNAME` to be `john`, you would write:
   
   ```bash
   DB_USERNAME=john
   ```
   
   These can also be set as [environment variables](https://en.wikipedia.org/wiki/Environment_variable).
7. Download the different data for [nltk](https://www.nltk.org/data.html), used for word tokenizing, removing stop words and the like. You can do this by running `python dataontosearch.py nltk_data`.


## Usage

There is only one script you need to care about, namely `dataontosearch.py`. It
has many subcommands that can be invoked, much like Django's `manage.py` command
or the `git` utility.

Documentation for the available subcommands and their arguments is not
presented here, instead you should use the `--help` flag to access the built-in
help. For example, to see the available subcommands, run:

`python dataontosearch.py --help`

Nothing is actually done when you use the `--help` flag, it simply prints the
help information and exits. Absolutely all subcommands accept the `--help` flag,
so please use it to your heart's content!

Below, some general information is provided about how to use DataOntoSearch.
Afterwards, the process of getting the search system into a usable state is
described.


### Entities

There are four types of RDF graphs in the application's database:

1. **Ontology**: Concepts and their relation to one another
2. **Dataset**: Available datasets in DCAT format
3. **Similarity**: Similarity graph, linking datasets to concepts manually
4. **Autotag**: Similarity graph, linking datasets to concepts automatically

These entities are managed through their own subcommands, in a fairly consistent
way. They all have a canonical version, which is used by default. It is also
possible to load a custom graph into the database.

In addition, there are different kinds of matrices used:

1. **Concept-concept similarity matrix**: Similarities between concepts,
   calculated using Wu-Palmer similarity.
2. **Concept-dataset similarity matrix for manual tagging**: Similarities
   between datasets and concepts, enriched by the concept-concept similarity
   matrix.
3. **Concept-dataset similarity matrix for automatic tagging**: Same as above,
   except this uses the _autotag_ graph rather than the _similarity_ one.
   
Since they are all derivatives of graphs, they are automatically created when
needed, and re-created whenever the graph they directly depend on (ontology, 
similarity and autotag respectively) changes or is otherwise updated.


### Choosing graphs to use

For each of the graphs mentioned above, the application's choice of graph to
use is done like this:

1. Has a UUID been specified using CLI options or the like (where available)?
   If so, use the specified graph.
2. Has a UUID been specified using the environment variable named 
   `<GRAPH-NAME>_UUID`, where `<GRAPH-NAME>` is the upper-cased name of the
   graph? For example, ONTOLOGY_UUID or DATASET_UUID. If so, use the specified
   graph.
3. If no graph has been specified this far, then whatever graph is returned
   first by MongoDB is used. The system will warn you about this, since there is
   no guarantee that the same graph would be returned at a later time.


#### Defining environment variables in `.env`

As a shortcut for defining environment variables (step 2 above), the
DataOntoSearch supports the [use of a `.env` file][env-usage] (sometimes called
"dotenv"). There you can define environment variables which could potentially be
tiresome to define in your shell every time. The system will print a message
whenever it reads from a `.env` file; if you don't receive such a message then
you can assume it wasn't read.

[env-usage]: https://github.com/theskumar/python-dotenv#usages


#### The Configuration entity
There is one exception to the procedure above, namely the **Configuration**
mechanism. A Configuration is simply a selection of graphs, one for each type,
which is stored alongside a label. The purpose of a Configuration is to allow
clients to connect to DataOntoSearch and simply specify their configuration,
from which the system knows what graphs to load. This way, different
organizations may connect to the same DataOntoSearch process, yet use different
ontologies, datasets and taggings.

Configurations are used by the dataset tagger (`dataset_tagger`) and the search
itself (`serve`) along with related commands (`search`, `multisearch` and
`evaluate`). The selection of a Configuration follows the exact same procedure
as for graph selection above, using the `CONFIGURATION_UUID` environment
variable when the user does not specify a Configuration themselves, or using
whatever Configuration MongoDB returns first.

The Configuration is not used for any other commands. The reason is that a
**Configuration requires there to be one graph of each type**, since it will be
pointing to one graph of each type. Therefore, you cannot create a Configuration
before everything else has been set up; it will generally be the last thing you
do before the search is ready.


#### Suggested approaches

* Keep only one version of each graph type, so it is obvious which one
  is picked by MongoDB.
  * You don't need to specify what graph to use this way.
  * However, if there are more than one graph, you may encounter subtle bugs
    due to an unexpected graph being used.
* Specify the UUID of the graph to use in the `.env` file, using the appropriate
  environment variables.
  * Works well when you'd like to switch between different graphs.
  * You may override the `.env` variables on the command line.
  * Though this means you must manage the UUIDs of graphs.
  * You can use multiple files and change between them by renaming one of them
    to `.env`, and let the others have other names when not in use.


### Setup

Before the search engine can get up and running, there are a couple processes
that must be run. Specifically:

1. Pre-process ontology
   1. Upload ontology
2. Pre-process datasets
   1. Import (new) datasets
   2. Perform manual linking to concepts
   3. Perform automatic linking to concepts
3. Run search

Below, you'll find instructions for running these processes.


### Pre-processing of ontology

#### Upload ontology

1. Run `python dataontosearch.py ontology create`

There are other commands you can use to manipulate and display ontologies, run `python dataontosearch.py ontology --help` for a full list.

### Pre-processing of datasets

#### Import (new) datasets

You may decide to import a set of dataset, or all datasets available to a CKAN instance or another compatible system. You will typically do this if you want to use the automatic tagger or the spreadsheet approach below:

1. Run `python dataontosearch.py dataset create --ckan <CKAN-URL>`
   where you replace `<CKAN-URL>` with the base URL to your CKAN instance. The
   instance must also expose RDF information about each dataset, using the ckanext-dcat plugin.

If you use another system which exposes the datasets using the DCAT vocabulary, you can import its data by downloading the RDF and using the `--read` flag with `python dataontosearch.py dataset create`.

Alternatively, you may start with an empty graph. This is useful when you intend to add datasets gradually through the dataset_tagger, which automatically downloads dataset metadata for unknown datasets. Simply use the `--empty` flag.

As always, run `python dataontosearch.py dataset create --help` to see your options.


#### Perform manual linking to concepts

You may use the existing tags for the Open Transport Data project, if you use the very same datasets. Simply run:

`python dataontosearch.py similarity create`

Alternatively, you can do custom tagging. There are two ways:

* **Using a spreadsheet**: This approach is preferred for mass-tagging of many
  datasets at once.
  1. Ensure the newly created ontology and dataset graphs are set to be used.
  See the instructions above on "Choosing graphs to use".
  2. Use `python dataontosearch.py similarity csv_prepare` to generate a CSV
     file which can be filled in.
  3. Read the instructions found when running `python dataontosearch.py similarity csv_parse --help` for information on the two options you have for filling in the CSV file.
  4. Fill the CSV file with your taggings, potentially using `python dataontosearch.py ontology show_hier` to see a list of available concepts.
  5. Export a new CSV file with your manual tagging.
  6. Use `python dataontosearch similarity csv_parse` to make the CSV file into
     an RDF graph, which you should save to a file.
  7. Use the `--read` option with `python dataontosearch similarity create` to
     store the newly create graph in the database.
     
* **Using online application**: This approach is preferred when incrementally
  adding datasets, for example when used with a running CKAN instance.

  1. Run `python dataontosearch.py similarity create --empty` to create a new,
     empty similarity graph.
  2. You must set up a Configuration before running the dataset tagger. This
     requires you to have an autotag graph already, so you may choose to
     continue with this set-up procedure. Alternatively, you can create a new,
     empty autotag graph by running `python dataontosearch.py autotag create
     --empty`. Then you can create a new
     Configuration using this empty autotag graph.
  3. Run `python dataontosearch.py dataset_tagger`
  4. Now, you can use the included interface for tagging datasets, or use the
     API with e.g. [the CKAN DataOntoSearch plugin][ckanext-dataontosearch] to tag datasets. Follow these steps to use
     the built-in interface:
  5. Visit http://localhost:8000 in your web browser.
  6. Fill in the UUID of the Configuration you have created (in step 2).
  7. Follow the instructions to tag datasets.

[ckanext-dataontosearch]: https://pypi.org/project/ckanext-dataontosearch/


#### Perform automatic linking to concepts

Run the following:

`python dataontosearch.py autotag create`

Again, append `--help` to see available options, for example options for using
English WordNet instead of Norwegian (the default).

**WARNING 1**: The autotag script requires around 2 GB of RAM(!) for the Python
process when using the Norwegian OrdNet, meaning that it may get killed on
systems with not enough memory. You may choose to run the autotag process on a
different system, instead of on the server intended for serving the search (for
example, use `generate` instead of `create`, then transfer the generated file).

**WARNING 2**: This script can take a long time to run, like 45 minutes or even an hour.
It is not able to continue where it left out, so you might want to run this in
`tmux`, `screen` or something similar when running on a server over SSH (so the
process survives if your SSH connection ends).


### Create Configuration

Before you can search, you must create a Configuration to be used by the search engine. Ensure
that the correct graphs will be chosen by running:

`python dataontosearch.py configuration create <LABEL NAME> --preview`

Replace `<LABEL NAME>` with a name for this Configuration so you can understand
which Configuration is used for what purpose later on.

This prints the UUID of the graphs that will be chosen for the new configuration.
Use the command line arguments available or set the environment variables if the
wrong graphs are chosen, or there is a mismatch between the graphs (the
similarity and autotag graphs must have been made using the same dataset and
ontology graphs).

When satisfied, remove the `--preview` flag to actually create the
Configuration.

### Run search

Now that you have a Configuration to use, you can start the search process:

1. Run `python dataontosearch.py serve`
2. The webserver will perform some indexing, creating necessary matrices. It
will give you a signal when it's done
3. You may now search by visiting http://localhost:8000

Alternatively, you may search using the command line interface directly.
Run `python dataontosearch.py search --help` for more information.

**Note:**
The web interface only allows access to the default Configuration. The API,
however, allows the user to specify a Configuration to use. With this setup, new
Configurations can be added or changed without restarting the web server. You
will need to re-generate the matrices, however, since it cannot be done inside a
request (the request would be aborted before the calculations are done). You can
do this by running `python dataontosearch.py matrix`, which you might want to
run periodically so changes in the manual tagging and dataset graphs are picked
up. You can add it as a recurring task in a crontab, though you'll need to point to the `python` executable located in your virtualenv, not just the system-wide `python`.

Do you want to run multiple queries for machine processing, while varying
available thresholds and such? Use the `python dataontosearch.py multisearch`
subcommand for this. See its `--help` information for _many_ details.

An evaluation subcommand is built on top of the `multisearch` command, allowing
you to run systematic evaluations. See `python dataontosearch.py evaluate
--help` for an introduction.
