const SUPABASE_URL = "https://ehoryvmipibaugrjrwzp.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;

exports.handler = async (event) => {
  if (event.httpMethod !== "DELETE") {
    return { statusCode: 405, body: JSON.stringify({ message: "Method not allowed" }) };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return { statusCode: 400, body: JSON.stringify({ message: "Invalid JSON" }) };
  }

  const { id, password } = body;
  if (!id || !password) {
    return { statusCode: 400, body: JSON.stringify({ message: "필수 값 누락" }) };
  }

  const headers = {
    apikey: SUPABASE_SERVICE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
  };

  const isAdmin = password === ADMIN_PASSWORD;

  if (!isAdmin) {
    const fetchRes = await fetch(
      `${SUPABASE_URL}/rest/v1/comments?id=eq.${id}&select=password`,
      { headers }
    );
    const rows = await fetchRes.json();
    if (!rows.length || rows[0].password !== password) {
      return { statusCode: 403, body: JSON.stringify({ message: "비밀번호가 틀렸습니다." }) };
    }
  }

  const delRes = await fetch(
    `${SUPABASE_URL}/rest/v1/comments?id=eq.${id}`,
    { method: "DELETE", headers }
  );

  return {
    statusCode: delRes.ok ? 200 : 500,
    body: JSON.stringify({ ok: delRes.ok }),
  };
};
