import React, { useEffect, useState, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  BarChart,
  Bar,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";

import { getAdminStatsSummary } from "../utils/adminApi";

// 최근 N일 날짜 배열 만들어주는 헬퍼 (오늘 기준)
function buildLastNDaysMap(n, valueKey) {
  const arr = [];
  const now = new Date();

  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);

    // "MM/DD" 형태로 포맷
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    arr.push({
      day: `${mm}/${dd}`,
      [valueKey]: 0,
    });
  }
  return arr;
}

// 서버에서 온 rawStats를 위에서 만든 기본 7일 배열에 merge
function mergeStats(baseArr, serverArr, valueKey) {
  // serverArr: [{ day:"10/29", uploads: 9 }, ...] 이런 식
  const map = {};
  for (const row of serverArr || []) {
    map[row.day] = row[valueKey] ?? 0;
  }

  return baseArr.map((base) => {
    if (map[base.day] != null) {
      return { ...base, [valueKey]: map[base.day] };
    }
    return base;
  });
}

export default function AdminDashboardMain() {
  // 로딩 / 에러
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg] = useState("");

  // 상단 카드용 지표
  const [totalUsers, setTotalUsers] = useState(0);
  const [newUsers30d, setNewUsers30d] = useState(0);
  const [withdraw30d, setWithdraw30d] = useState(0);

  // 그래프용 원본(서버)
  const [uploadStatsRaw, setUploadStatsRaw] = useState([]);
  const [visitStatsRaw, setVisitStatsRaw] = useState([]);

  // 서버에서 데이터 로드
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setErrMsg("");

        const data = await getAdminStatsSummary();

        setTotalUsers(data.totalUsers ?? 0);
        setNewUsers30d(data.newUsers30d ?? 0);
        setWithdraw30d(data.withdraw30d ?? 0);

        setUploadStatsRaw(Array.isArray(data.dailyUploads7d) ? data.dailyUploads7d : []);
        setVisitStatsRaw(Array.isArray(data.dailyVisits7d) ? data.dailyVisits7d : []);
      } catch (e) {
        console.error(e);
        setErrMsg("통계 데이터를 불러오지 못했습니다.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // 차트용 7일 보정 데이터
  const uploadStats = useMemo(() => {
    // 기본 7일 [{day:'MM/DD', uploads:0}, ...]
    const base = buildLastNDaysMap(7, "uploads");
    return mergeStats(base, uploadStatsRaw, "uploads");
  }, [uploadStatsRaw]);

  const visitStats = useMemo(() => {
    // 기본 7일 [{day:'MM/DD', visits:0}, ...]
    const base = buildLastNDaysMap(7, "visits");
    return mergeStats(base, visitStatsRaw, "visits");
  }, [visitStatsRaw]);

  // 도넛 차트 데이터
  const pieData = useMemo(() => {
    const baseUsers = Math.max(totalUsers - newUsers30d - withdraw30d, 0);
    return [
      { name: "기존 회원", value: baseUsers },
      { name: "신규 회원", value: newUsers30d },
      { name: "탈퇴 회원", value: withdraw30d },
    ];
  }, [totalUsers, newUsers30d, withdraw30d]);

  // 도넛 색상 팔레트
  const PIE_COLORS = ["#C8C8C8", "#FF54A1", "#2d2385ff"];

  // -------- UI 렌더링 --------

  // 로딩 상태
  if (loading) {
    return (
      <div className="text-[13px] text-gray-700 text-center py-10">
        대시보드 데이터를 불러오는 중입니다...
      </div>
    );
  }

  // 에러 상태
  if (errMsg) {
    return (
      <div className="text-center py-10">
        <div className="text-[14px] font-medium text-red-600">{errMsg}</div>
        <div className="text-[12px] text-gray-500 mt-2 leading-relaxed">
          ※ 관리자 권한이 없거나 서버와의 통신에 실패했을 수 있습니다.
        </div>
      </div>
    );
  }

  // 정상 상태
  return (
    <div className="text-[13px] text-gray-900 space-y-4">
      {/* 메인 카드 래퍼 */}
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm space-y-4">
        {/* 1행: 회원 통계 + 업로드 차트 */}
        <div className="flex flex-col lg:flex-row gap-4">
          {/* 회원 통계 카드 */}
          <div className="lg:w-[320px] w-full flex-shrink-0 rounded-md border border-gray-200 bg-gray-50 p-4">
            {/* 카드 헤더 */}
            <div className="flex items-start justify-between mb-3">
              <div className="text-[12px] font-medium text-gray-800">
                총 회원수 / 신규 가입 / 탈퇴
                <span className="block text-[11px] text-gray-500 font-normal">
                  (최근 30일)
                </span>
              </div>
            </div>

            {/* 숫자 영역 */}
            <div className="flex justify-between mb-4 text-[12px]">
              <div>
                <div className="text-gray-600">총 회원수</div>
                <div className="text-[20px] font-semibold text-gray-900 leading-tight">
                  {totalUsers.toLocaleString()}
                </div>
              </div>

              <div className="text-right">
                <div className="text-gray-600">신규 가입</div>
                <div className="text-[16px] font-semibold text-pink-600 leading-tight">
                  +{newUsers30d}
                </div>

                <div className="text-gray-600 mt-2">탈퇴</div>
                <div className="text-[13px] font-semibold text-gray-700 leading-tight">
                  {withdraw30d}
                </div>
              </div>
            </div>

            {/* 도넛 차트 */}
            <div className="h-[170px]">
              <ResponsiveContainer width="100%" height="100%" minWidth={100} minHeight={100}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={65}
                    paddingAngle={3}
                  >
                    {pieData.map((entry, idx) => (
                      <Cell
                        key={`cell-${idx}`}
                        fill={PIE_COLORS[idx % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => [`${v}명`, ""]} />
                  <Legend
                    verticalAlign="bottom"
                    height={25}
                    wrapperStyle={{ paddingTop:"15px",fontSize: "11px" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 업로드 수 차트 카드 */}
          <div className="flex-1 min-w-[280px] rounded-md border border-gray-200 bg-gray-50 p-4">
            <div className="flex justify-between text-[12px] mb-2">
              <span className="font-medium text-gray-800">업로드 수</span>
              <span className="text-[11px] text-gray-500">최근 7일</span>
            </div>

            <div className="h-[280px] rounded-md border border-gray-300 bg-white p-2">
              <ResponsiveContainer width="100%" height="100%" minWidth={100} minHeight={100} >
                <BarChart
                  data={uploadStats}
                  margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
                  barCategoryGap="25%"
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false}   />
                  <Tooltip />
                  <defs>
                    <linearGradient id="colorUploads" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#FF54A1" />
                      <stop offset="100%" stopColor="#B862FF" />
                    </linearGradient>
                  </defs>
                  <Bar
                    dataKey="uploads"
                    radius={[4, 4, 0, 0]}
                    fill="url(#colorUploads)"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 2행: 방문자(접속자 수) 라인 차트 */}
        <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
          <div className="flex justify-between text-[12px] mb-2">
            <span className="font-medium text-gray-800">접속자 수</span>
            <span className="text-[11px] text-gray-500">최근 7일</span>
          </div>

          <div className="h-[200px] rounded-md border border-gray-300 bg-white p-3">
            <ResponsiveContainer width="100%" height="100%" minWidth={100} minHeight={100}>
              <LineChart
                data={visitStats}
                margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="visits"
                  stroke="#FF54A1"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

      
      </section>
    </div>
  );
}