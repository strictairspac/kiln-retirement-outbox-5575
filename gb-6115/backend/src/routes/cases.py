from fastapi import APIRouter, Depends

from src.config.resources import engine
from src.controllers.access import identity, operator
from src.controllers.workbench import new_case, new_run
from src.schemas.cases import BatchEntry, CaseEntry, CaseInput, CaseResult
from src.schemas.runs import RunEntry, RunInput
from src.services import cases

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("", response_model=list[CaseEntry], dependencies=[Depends(identity)])
def list_cases():
    with engine.connect() as db:
        return cases.list_entries(db)


@router.get("/batches", response_model=list[BatchEntry], dependencies=[Depends(identity)])
def list_batches():
    """炉体退役批次页的正式判定：占号、退回原因、失败释放和进档张数。"""
    with engine.connect() as db:
        return cases.ledger(db)


@router.get("/{case_id}", response_model=CaseEntry, dependencies=[Depends(identity)])
def case_detail(case_id: int):
    with engine.connect() as db:
        return cases.get(db, case_id)


@router.post("", response_model=CaseResult, status_code=201)
def register(form: CaseInput, user=Depends(operator)):
    return new_case(form, user)


@router.post("/{case_id}/runs", response_model=RunEntry, status_code=202)
def schedule(case_id: int, form: RunInput, user=Depends(operator)):
    return new_run(case_id, form, user)
