from pydantic import BaseModel
from typing import List, Optional

class DailyUploadStat(BaseModel):
    day: str       # "10/24"
    uploads: int   # 63

class DailyVisitStat(BaseModel):
    day: str       # "10/24"
    visits: int    # 171

class AdminStatsSummary(BaseModel):
    totalUsers: int
    newUsers30d: int
    withdraw30d: int
    dailyUploads7d: List[DailyUploadStat]
    dailyVisits7d: List[DailyVisitStat]

class AdminFileItem(BaseModel):
    id: int
    nickname: str
    filename: str
    uploadedAt: str
    ext: str
    size: int
    status: str
    lastErrorMsg: Optional[str] = None
    deletedAt: Optional[str] = None

class AdminFileStats(BaseModel):
    all: int      
    done: int     
    failed: int   

class AdminFileListResponse(BaseModel):
    total: int               
    items: List[AdminFileItem]
    stats: AdminFileStats