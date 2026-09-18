import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from schemas import (
    OptimizeEnergyRequest,
    OptimizeEnergyResponse,
    HealthResponse,
    DirectiveInterpretationEntry,
    HourlyPlanEntry
)
from llm_interpreter import interpret_operator_notes
from guardrails import validate_and_guardrail_interpretations
from optimizer import solve_optimization
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gridwise")

app = FastAPI(
    title="GridWise API",
    description="Smart Campus Energy Optimization API with LLM Operator Directive Interpretation",
    version="2.0.0"
)


@app.get("/", tags=["Health"])
async def root():
    """Service discovery endpoint for browsers and live demos."""
    return {
        "service": "GridWise",
        "status": "ok",
        "health": "/health",
        "optimize": "/optimize-energy"
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Returns HTTP 400 for malformed or structurally invalid requests."""
    logger.warning(f"Request validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Malformed JSON or structurally invalid request", "details": str(exc)}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Controlled internal error handler to avoid leaking secrets or raw stack traces."""
    logger.error(f"Internal error processing request: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal processing error occurred."}
    )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Readiness endpoint for the judging harness."""
    return HealthResponse(status="ok")


@app.post("/optimize-energy", response_model=OptimizeEnergyResponse, tags=["Optimization"])
async def optimize_energy(req: OptimizeEnergyRequest):
    """
    Main LLM interpretation + 24-hour campus energy scheduling endpoint.
    1. Interprets natural-language operator notes via LLM.
    2. Enforces deterministic guardrails.
    3. Solves optimal energy dispatch matching all physics & directive constraints.
    """
    try:
        battery_dict = req.battery.model_dump()
        hours_dicts = [h.model_dump() for h in req.hours]

        # 1. LLM Interpretation
        raw_interpretations = interpret_operator_notes(
            req.operator_notes,
            battery_dict
        )

        # 2. Guardrails validation and normalization
        cleaned_interpretations = validate_and_guardrail_interpretations(
            raw_interpretations,
            req.operator_notes,
            battery_dict
        )

        # 3. Filter active directives and count distractors
        active_directives = [d for d in cleaned_interpretations if d.get("applies", False)]
        ignored_count = len([d for d in cleaned_interpretations if not d.get("applies", False)])

        # 4. Mathematical Optimization
        hourly_plan, total_grid, total_cost, peak_grid, plan_summary = solve_optimization(
            hours_data=hours_dicts,
            battery_data=battery_dict,
            valid_directives=active_directives,
            ignored_count=ignored_count
        )

        # 5. Format response
        response = OptimizeEnergyResponse(
            scenario_id=req.scenario_id,
            directive_interpretation=[
                DirectiveInterpretationEntry(**item) for item in cleaned_interpretations
            ],
            hourly_plan=[
                HourlyPlanEntry(**item) for item in hourly_plan
            ],
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak_grid,
            plan_summary=plan_summary
        )

        return response

    except Exception as e:
        logger.error(f"Error in optimize_energy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate energy optimization schedule."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
