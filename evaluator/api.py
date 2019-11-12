# This is a component of the MMVB for the "Symptom assessment" sub-group
# (of the the International Telecommunication Union focus group
# "Artificial Intelligence for Health".
# For copyright and licence, see the parent directory.

import glob
import hashlib
import json
import os
import time

import requests

from evaluator.benchmark.manager import BenchmarkManager
from evaluator.benchmark.exceptions import SetupError
from evaluator.benchmark.utils import create_dirs
from evaluator.benchmark.definitions import ManagerStatuses

SERVER_HOST_FOR_CASE_GENERATION = "http://0.0.0.0:5001"

TIMEOUT = 5.0  # in seconds

FILE_DIR = os.path.dirname((os.path.abspath(__file__)))

AI_LOCATION_ALPHA = "http://127.0.0.1:5002/toy-ai/v1/"
DEFAULT_HEALTH_CHECK_ENDPOINT_NAME = 'health-check'
DEFAULT_SOLVE_CASE_ENDPOINT_NAME = 'solve-case'

# TODO: make this configurable each ai can implement and have its own root url
# TODO: as well as its own health check and solve case endpoints
AI_TYPES_ENDPOINTS = {
    'toy_ai_random_uniform': {
        'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        'solve_case': AI_LOCATION_ALPHA + DEFAULT_SOLVE_CASE_ENDPOINT_NAME,
    },
    'toy_ai_random_probability_weighted': {
        'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        'solve_case': AI_LOCATION_ALPHA + DEFAULT_SOLVE_CASE_ENDPOINT_NAME,
    },
    'toy_ai_deterministic_most_likely_conditions': {
        'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        'solve_case': AI_LOCATION_ALPHA + DEFAULT_SOLVE_CASE_ENDPOINT_NAME,
    },
    'toy_ai_deterministic_by_symptom_intersection': {
        'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        'solve_case': AI_LOCATION_ALPHA + DEFAULT_SOLVE_CASE_ENDPOINT_NAME,
    },
    'toy_ai_faulty_random_uniform': {
        'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        'solve_case': AI_LOCATION_ALPHA + DEFAULT_SOLVE_CASE_ENDPOINT_NAME,
    },
    'babylon_toy_ai': {
        'health_check': "http://127.0.0.1:5006/toy-ai/v1/health-check",
        'solve_case': "http://127.0.0.1:5006/toy-ai/v1/solve-case",
    }
}

try:
    from extra_ai_links import EXTRA_LINKS
    for key, value in EXTRA_LINKS.items():
        AI_TYPES_ENDPOINTS[key] = {
            'solve_case': value,
            # just for now:
            'health_check': AI_LOCATION_ALPHA + DEFAULT_HEALTH_CHECK_ENDPOINT_NAME,
        }
except:
    pass

# DEPRECATE THIS:
AI_TYPES_TO_LOCATIONS = {}
for key, value in AI_TYPES_ENDPOINTS.items():
    AI_TYPES_TO_LOCATIONS[key] = (
        value['solve_case']
    )

# TODO: delete all benchmarks from this dictionary
# and from the database after some timeout
BENCHMARK_MANAGERS = {}


def get_unique_id():
    return str(time.time()).replace(".", "_")


def parse_validate_caseSetId(caseSetId):
    case_set_id = str(caseSetId)
    for char in case_set_id:
        assert char in [str(x) for x in range(10)] or char == "_"
    return case_set_id


def md5(value):
    return hashlib.md5(value.encode()).hexdigest()


def generate_case_set(request):
    num_cases = int(request["numCases"])
    # TODO: Gracefully fail for >200 cases
    assert num_cases > 0 and num_cases <= 200

    cases = []

    for case_id in range(num_cases):
        request = requests.get(
            SERVER_HOST_FOR_CASE_GENERATION + "/case-generator/v1/generate-case"
        )
        assert request.status_code == 200
        cases.append(request.json())

    case_set_id = get_unique_id()
    path = os.path.join(FILE_DIR, "data", case_set_id)

    create_dirs(path)

    json.dump(cases, open(os.path.join(path, "cases.json"), "w"), indent=2)

    return {"case_set_id": case_set_id}


def list_case_sets():
    path = os.path.join(FILE_DIR, "data/")

    return {
        "existing_case_sets": [
            element.replace(path, "") for element in glob.glob(path + "*")
        ]
    }


def extract_case_set(caseSetId):
    case_set_id = parse_validate_caseSetId(caseSetId)

    return {
        "cases": json.load(
            open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json"))
        )
    }


def list_all_ai_implementations():
    return {
        "ai_implementations": [
            {"name": ai_implementation_name}
            for ai_implementation_name in AI_TYPES_TO_LOCATIONS.keys()
        ]
    }


def create_benchmark_manager():
    unique_id = get_unique_id()
    BENCHMARK_MANAGERS[unique_id] = BenchmarkManager()
    return {
        'benchmarkManagerId': unique_id,
    }


def run_case_set_against_ais(request):
    """Runs a given case set against a given set of AIs"""

    unique_id = request['benchmarkManagerId']

    benchmark_manager = BENCHMARK_MANAGERS[unique_id]

    assert benchmark_manager.state == ManagerStatuses.IDLE

    case_set_id = parse_validate_caseSetId(request["caseSetId"])
    ai_implementations = request["aiImplementations"]
    results = []

    for ai in ai_implementations:
        assert ai in AI_TYPES_ENDPOINTS, f'AI {ai} not recognised/configured'

    benchmarked_ais = {
        ai: AI_TYPES_ENDPOINTS[ai]
        for ai in ai_implementations
    }

    cases = json.load(
        open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json"))
    )

    try:
        benchmark_manager.setup(unique_id, case_set_id, cases, benchmarked_ais)
    except SetupError:
        unique_id = benchmark_manager.benchmark_id
        # at this point we might also like to take the case set being run and
        # load it into the UI proper container
        return {'run_id': unique_id, 'status': int(ManagerStatuses.RUNNING)}
    else:
        output = benchmark_manager.run_benchmark()
        results = output['results']
        json.dump(
            results,
            open(os.path.join(FILE_DIR, "data", case_set_id, "results.json"), "w"),
            indent=2)

    results_by_ai = {}
    if results:
        for _, ais_results in results.items():
            for ai_name, ai_result in ais_results.items():
                results_by_ai.setdefault(ai_name, []).append(ai_result['result'])

    return {
        'run_id': unique_id,
        'case_set_id': case_set_id,
        'case_set': cases,
        'status': int(ManagerStatuses.IDLE),
        'results_by_ai': results_by_ai
        }


# def run_case_set_against_ai(request):
#     case_set_id = parse_validate_caseSetId(request["caseSetId"])
#     ai_implementation = request["aiImplementation"]
#     run_name = request["runName"]

#     assert ai_implementation in AI_TYPES_TO_LOCATIONS
#     ai_location_path = AI_TYPES_TO_LOCATIONS[ai_implementation]

#     run_hash = get_unique_id()

#     path = os.path.join(FILE_DIR, "data", case_set_id, run_hash)

#     cases = json.load(open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json")))

#     results = []

#     for case in cases:
#         try:
#             request = requests.post(
#                 ai_location_path,
#                 json={
#                     "aiImplementation": ai_implementation,
#                     "caseData": case["caseData"],
#                 },
#                 timeout=TIMEOUT,
#             )

#             assert request.status_code == 200
#             response = request.json()
#         except AssertionError:
#             response = None

#         results.append(response)

#     create_dirs(path)

#     json.dump(
#         {
#             "ai_location_path": ai_location_path,
#             "ai_implementation": ai_implementation,
#             "run_name": run_name,
#         },
#         open(os.path.join(path, "meta.json"), "w"),
#         indent=2,
#     )

#     json.dump(results, open(os.path.join(path, "results.json"), "w"), indent=2)

#     return {"runId": run_hash, "results": results}


def report_update(request):
    benchmarkId = request['benchmarkId']
    manager = BENCHMARK_MANAGERS[benchmarkId]
    report = manager.db_client.select_manager_report(
        benchmark_id=manager.benchmark_id, prefetch=True)

    collected_reports = {}
    for ai_report in report.ai_reports:
        collected_reports.setdefault(ai_report.ai_name, []).append(
            {
                'case_status': ai_report.case_status,
                'healthcheck_status': ai_report.healthcheck_status,
                'health_checks': ai_report.health_checks,
                'errors': ai_report.errors,
                'timeouts': ai_report.hard_timeouts
            }
        )

    results_file_path = os.path.join(
        FILE_DIR, "data", manager.case_set_id, "results.json")

    if manager.state == ManagerStatuses.IDLE and os.path.isfile(results_file_path):
        results = json.load(open(
            os.path.join(FILE_DIR, "data", manager.case_set_id, "results.json"), "r")
        )
        results_by_ai = {}
        if results:
            for _, ais_results in results.items():
                for ai_name, ai_result in ais_results.items():
                    results_by_ai.setdefault(ai_name, []).append(ai_result['result'])
    else:
        results_by_ai = {}

    output = {
        'run_id': manager.benchmark_id,
        'case_set_id': manager.case_set_id,
        'total_cases': report.total_cases,
        'current_case_index': report.current_case_index,
        'current_case_id': report.current_case_id,
        'ai_reports': collected_reports,
        'results_by_ai': results_by_ai,
        'logs': manager.accumulated_logs
    }

    return output


# def benchmark_status():
#     return {'status': bool(int(BENCHMARK_MANAGER.state))}
