from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from typing import Optional
import os, uuid, aiofiles
from app.schemas.withdrawal_schema import WithdrawalRequest, WithdrawalAction
from app.services.withdrawal_service import (
    create_withdrawal_request, get_publisher_withdrawals,
    get_all_withdrawals, process_withdrawal, delete_withdrawal,
)
from app.dependencies import get_db, get_current_active_publisher, get_current_admin
from app.core.exceptions import ValidationError, NotFoundError

router = APIRouter(prefix="/withdrawals", tags=["Withdrawals"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "withdrawals")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("", status_code=201)
async def request_withdrawal(
    data: WithdrawalRequest,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    try:
        withdrawal_id = await create_withdrawal_request(
            current_user["id"], current_user["name"], data.model_dump(), db,
        )
        return {"success": True, "withdrawal_id": withdrawal_id, "message": "Withdrawal request submitted"}
    except ValueError as e:
        raise ValidationError(str(e))


@router.get("/my")
async def my_withdrawals(
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    withdrawals = await get_publisher_withdrawals(current_user["id"], db)
    for w in withdrawals:
        if w.get("requested_at"):
            w["requested_at"] = w["requested_at"].isoformat()
        if w.get("processed_at"):
            w["processed_at"] = w["processed_at"].isoformat()
    return {"success": True, "withdrawals": withdrawals}


@router.get("/admin")
async def admin_withdrawals(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    skip = (page - 1) * limit
    withdrawals = await get_all_withdrawals(db, status=status, skip=skip, limit=limit)
    total = await db.withdrawals.count_documents({"status": status} if status else {})
    for w in withdrawals:
        if w.get("requested_at"):
            w["requested_at"] = w["requested_at"].isoformat()
        if w.get("processed_at"):
            w["processed_at"] = w["processed_at"].isoformat()
    return {
        "success": True, "withdrawals": withdrawals,
        "total": total, "page": page, "pages": (total + limit - 1) // limit,
    }


@router.patch("/{withdrawal_id}")
async def process_withdrawal_endpoint(
    withdrawal_id: str,
    data: WithdrawalAction,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    try:
        updated = await process_withdrawal(withdrawal_id, data.action, data.transaction_id, data.admin_note, db)
        if not updated:
            raise NotFoundError("Withdrawal")
        return {"success": True, "message": f"Withdrawal {data.action}d successfully"}
    except ValueError as e:
        raise ValidationError(str(e))


@router.post("/{withdrawal_id}/pay")
async def pay_withdrawal(
    withdrawal_id: str,
    transaction_id: str = Form(...),
    admin_note: Optional[str] = Form(None),
    proof_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Mark withdrawal as paid with optional proof file upload."""
    proof_url = None
    if proof_file and proof_file.filename:
        ext = os.path.splitext(proof_file.filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}:
            raise ValidationError("Only image and PDF files are allowed")
        filename = f"{withdrawal_id}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await proof_file.read())
        proof_url = f"/uploads/withdrawals/{filename}"

    try:
        updated = await process_withdrawal(withdrawal_id, "paid", transaction_id, admin_note, db)
        if not updated:
            raise NotFoundError("Withdrawal")
    except ValueError as e:
        raise ValidationError(str(e))

    if proof_url:
        from bson import ObjectId
        try:
            wid = ObjectId(withdrawal_id)
        except Exception:
            wid = withdrawal_id
        await db.withdrawals.update_one({"_id": wid}, {"$set": {"proof_url": proof_url}})

    return {"success": True, "message": "Withdrawal marked as paid", "proof_url": proof_url}


@router.put("/{withdrawal_id}/edit")
async def edit_withdrawal(
    withdrawal_id: str,
    transaction_id: Optional[str] = Form(None),
    admin_note: Optional[str] = Form(None),
    proof_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Edit transaction ID, admin note, or proof image on a withdrawal."""
    from bson import ObjectId
    from datetime import datetime
    try:
        wid = ObjectId(withdrawal_id)
    except Exception:
        wid = withdrawal_id

    existing = await db.withdrawals.find_one({"_id": wid})
    if not existing:
        raise NotFoundError("Withdrawal")

    update_fields: dict = {"updated_at": datetime.utcnow()}
    if transaction_id is not None:
        update_fields["transaction_id"] = transaction_id
    if admin_note is not None:
        update_fields["admin_note"] = admin_note

    if proof_file and proof_file.filename:
        ext = os.path.splitext(proof_file.filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}:
            raise ValidationError("Only image and PDF files are allowed")
        filename = f"{withdrawal_id}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await proof_file.read())
        update_fields["proof_url"] = f"/uploads/withdrawals/{filename}"

    await db.withdrawals.update_one({"_id": wid}, {"$set": update_fields})
    return {"success": True, "message": "Withdrawal updated"}


@router.delete("/{withdrawal_id}")
async def delete_withdrawal_endpoint(
    withdrawal_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    deleted = await delete_withdrawal(withdrawal_id, db)
    if not deleted:
        raise NotFoundError("Withdrawal")
    return {"success": True, "message": "Withdrawal deleted"}
