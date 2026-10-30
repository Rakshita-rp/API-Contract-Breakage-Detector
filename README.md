# API Contract Breakage Detector

A beginner-friendly Python project that compares two OpenAPI specifications and flags likely breaking changes before deployment.

## What is included?
- `api_v1.yaml`: old/baseline Student Management API contract.
- `api_v2.yaml`: proposed API with intentional breaking and non-breaking changes.
- `detector.py`: comparison tool.
- `.github/workflows/api-contract-check.yml`: example GitHub Actions workflow.
- `requirements.txt`: dependency list.

OpenAPI describes an API's endpoints, parameters, and request/response data structures. This project compares those descriptions; it does **not** call a live API or prove runtime behavior.

## Setup (Windows / VS Code)

1. Create/open this folder in VS Code.
2. Open Terminal → New Terminal.
3. Optional: create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. Install dependency:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the comparison:
   ```bash
   python detector.py api_v1.yaml api_v2.yaml
   ```
6. Save a JSON report:
   ```bash
   python detector.py api_v1.yaml api_v2.yaml --output report.json
   ```

## Expected findings in the sample
The detector should flag examples such as:
- `DELETE /students/{student_id}` was removed.
- `limit` changed from optional to required.
- `limit` changed from integer to string.
- `student_id` changed from integer to string.
- Response field `total` changed from integer to string.
- `Student.id` changed from integer to string.
- `Student.email` became required.
- `GET /courses` was added (reported as INFO, usually non-breaking).

Exact output depends on the checks implemented in `detector.py`.

## How it works
1. Load the old and new YAML documents.
2. Collect HTTP operations by path and method.
3. Compare operations and parameters.
4. Compare simple response schema fields and types.
5. Print a report and optionally save JSON.

## Limitations
This is a learning/demo implementation, not a full OpenAPI diff engine. It does not fully resolve nested references, `allOf`/`oneOf`/`anyOf`, request-body compatibility, authentication changes, response-code changes, enums, formats, or every OpenAPI edge case. Review findings before blocking a deployment.

## project conclusion
The API Contract Breakage Detector automates a basic comparison of two API specifications and highlights likely backward-incompatible changes. Running it before deployment can help developers find risky endpoint, parameter, and response-schema changes earlier. It can be extended with deeper schema analysis and continuous integration checks.

## Useful references
- OpenAPI Specification: https://spec.openapis.org/oas/
- OpenAPI Initiative FAQ: https://www.openapis.org/faq
