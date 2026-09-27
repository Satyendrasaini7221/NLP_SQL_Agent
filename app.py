from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from decimal import Decimal
from datetime import date, datetime

from agent import (
    generate_sql,
    run_query_with_repair,
    close_database
)


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="Business Intelligence SQL Agent",
    description="Natural Language Business Intelligence API",
    version="1.0.0"
)


# =========================================================
# FRONTEND
# =========================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


# =========================================================
# REQUEST MODEL
# =========================================================

class QuestionRequest(BaseModel):

    question: str


# =========================================================
# HOME / HEALTH CHECK
# =========================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": (
            "Business Intelligence SQL Agent "
            "is running"
        )
    }


# =========================================================
# FRONTEND PAGE
# =========================================================

@app.get("/ui")
def frontend():

    return FileResponse(
        "static/index.html"
    )


# =========================================================
# CONVERT DATABASE VALUES
# TO JSON-SAFE VALUES
# =========================================================

def make_json_safe(value):

    if isinstance(value, Decimal):

        return float(value)

    if isinstance(value, (datetime, date)):

        return value.isoformat()

    return value


# =========================================================
# PREPARE ROW DATA
# =========================================================

def prepare_data(columns, results):

    data = []

    for row in results:

        row_data = {}

        for column, value in zip(
            columns,
            row
        ):

            row_data[column] = make_json_safe(
                value
            )

        data.append(row_data)

    return data


# =========================================================
# CHECK NUMERIC VALUE
# =========================================================

def is_numeric(value):

    return isinstance(
        value,
        (int, float)
    ) and not isinstance(
        value,
        bool
    )


# =========================================================
# PREPARE VISUALIZATION DATA
# =========================================================

def create_visualization(
    task,
    columns,
    results
):

    # -----------------------------------------------------
    # No data
    # -----------------------------------------------------

    if not results:

        return {
            "chart_type": "none",
            "columns": columns,
            "data": [],
            "task": task
        }


    # -----------------------------------------------------
    # Convert database rows
    # -----------------------------------------------------

    data = prepare_data(
        columns,
        results
    )


    # -----------------------------------------------------
    # Single value KPI
    # -----------------------------------------------------

    if (
        len(results) == 1
        and len(columns) == 1
    ):

        return {
            "chart_type": "kpi",
            "columns": columns,
            "data": {
                "value": data[0][columns[0]],
                "label": columns[0]
            },
            "task": task
        }


    # -----------------------------------------------------
    # Single row result
    #
    # Example:
    #
    # product_name | revenue
    #
    # or
    #
    # customer_name | total_spent
    # -----------------------------------------------------

    if (
        len(results) == 1
        and len(columns) >= 2
    ):

        numeric_columns = []

        for column in columns:

            value = data[0].get(column)

            if is_numeric(value):

                numeric_columns.append(column)


        if numeric_columns:

            return {
                "chart_type": "kpi",
                "columns": columns,
                "data": data[0],
                "task": task
            }


    # -----------------------------------------------------
    # BAR CHART
    #
    # If result contains a descriptive column and
    # at least one numeric column.
    #
    # This works dynamically for:
    #
    # product + revenue
    # category + sales
    # customer + orders
    # etc.
    # -----------------------------------------------------

    if len(results) > 1:

        numeric_columns = []

        for column in columns:

            values = [
                row.get(column)
                for row in data
            ]

            if all(
                is_numeric(value)
                for value in values
            ):

                numeric_columns.append(column)


        # -------------------------------------------------
        # Use bar chart when exactly one useful numeric
        # measure exists.
        # -------------------------------------------------

        if len(numeric_columns) == 1:

            numeric_column = numeric_columns[0]

            label_column = None

            for column in columns:

                if column != numeric_column:

                    label_column = column
                    break


            if label_column:

                return {
                    "chart_type": "bar",
                    "columns": columns,
                    "data": data,
                    "label_column": label_column,
                    "value_column": numeric_column,
                    "task": task
                }


    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    return {
        "chart_type": "table",
        "columns": columns,
        "data": data,
        "task": task
    }


# =========================================================
# ASK BUSINESS QUESTION
# =========================================================

@app.post("/ask")
def ask_question(
    request: QuestionRequest
):

    # -----------------------------------------------------
    # Validate input
    # -----------------------------------------------------

    question = request.question.strip()


    if not question:

        return {
            "success": False,
            "message": (
                "Please enter a business question."
            )
        }


    # -----------------------------------------------------
    # Generate SQL plan
    # -----------------------------------------------------

    try:

        plan = generate_sql(
            question
        )

    except Exception:

        return {
            "success": False,
            "message": (
                "Sorry, I couldn't process "
                "the business question."
            )
        }


    # -----------------------------------------------------
    # Invalid AI response
    # -----------------------------------------------------

    if not plan:

        return {
            "success": False,
            "message": (
                "Sorry, I couldn't understand "
                "the business question."
            )
        }


    # -----------------------------------------------------
    # Execute query
    #
    # run_query_with_repair:
    #
    # 1. executes generated SQL
    # 2. if SQL fails, automatically attempts repair
    # 3. returns final successful result
    # -----------------------------------------------------

    try:

        (
            task,
            sql,
            results,
            columns
        ) = run_query_with_repair(
            question,
            plan
        )

    except Exception:

        return {
            "success": False,
            "message": (
                "Sorry, I couldn't retrieve "
                "the requested business information."
            )
        }


    # -----------------------------------------------------
    # Query failed
    # -----------------------------------------------------

    if (
        task is None
        or sql is None
        or results is None
        or columns is None
    ):

        return {
            "success": False,
            "message": (
                "Sorry, I couldn't retrieve "
                "the requested business information."
            )
        }


    # -----------------------------------------------------
    # Format answer
    # -----------------------------------------------------

    try:

        from agent import format_result

        answer = format_result(
            task,
            columns,
            results
        )

    except Exception:

        return {
            "success": False,
            "message": (
                "Sorry, I couldn't format "
                "the business result."
            )
        }


    # -----------------------------------------------------
    # Visualization
    # -----------------------------------------------------

    try:

        visualization = create_visualization(
            task,
            columns,
            results
        )

    except Exception:

        visualization = {
            "chart_type": "table",
            "columns": columns,
            "data": prepare_data(
                columns,
                results
            ),
            "task": task
        }


    # -----------------------------------------------------
    # JSON-safe result rows
    # -----------------------------------------------------

    safe_results = prepare_data(
        columns,
        results
    )


    # -----------------------------------------------------
    # FINAL API RESPONSE
    # -----------------------------------------------------

    return {
        "success": True,
        "question": question,
        "task": task,
        "sql": sql,
        "answer": answer,
        "columns": columns,
        "results": safe_results,
        "visualization": visualization
    }


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
def shutdown():

    close_database()