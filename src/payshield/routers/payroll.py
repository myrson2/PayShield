from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_payroll_record_service
from payshield.schema import PayrollRecordResponse
from payshield.model import UserModel
from payshield.service import PayrollRecordService

router = APIRouter()


@router.get("/me", response_model=PayrollRecordResponse)
async def get_my_payroll(
        current_user: Annotated[UserModel, Depends(get_current_user)],
        payroll_service: Annotated[PayrollRecordService, Depends(get_payroll_record_service)],
) -> PayrollRecordResponse:
    payroll_record = payroll_service.get_my_salary(user_id=current_user.id)
    if payroll_record is None:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    return payroll_record
