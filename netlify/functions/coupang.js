const crypto = require("crypto");

const DOMAIN = "https://api-gateway.coupang.com";
const ACCESS_KEY = process.env.COUPANG_ACCESS_KEY;
const SECRET_KEY = process.env.COUPANG_SECRET_KEY;

function generateHmac(method, url) {
  const [path, query] = url.split("?");
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const dt =
    String(now.getUTCFullYear()).slice(2) +
    pad(now.getUTCMonth() + 1) +
    pad(now.getUTCDate()) +
    "T" +
    pad(now.getUTCHours()) +
    pad(now.getUTCMinutes()) +
    pad(now.getUTCSeconds()) +
    "Z";
  const message = dt + method + path + (query || "");
  const signature = crypto
    .createHmac("sha256", SECRET_KEY)
    .update(message)
    .digest("hex");
  return `CEA algorithm=HmacSHA256, access-key=${ACCESS_KEY}, signed-date=${dt}, signature=${signature}`;
}

async function coupangApi(method, path, body) {
  const auth = generateHmac(method, path);
  const url = `${DOMAIN}${path}`;
  const options = {
    method,
    headers: {
      Authorization: auth,
      "Content-Type": "application/json;charset=UTF-8",
    },
  };
  if (body) options.body = JSON.stringify(body);
  const resp = await fetch(url, options);
  return resp.json();
}

exports.handler = async (event) => {
  const headers = {
    "Access-Control-Allow-Origin": "https://seunghan.xyz",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Content-Type": "application/json",
  };

  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers };
  }

  if (!ACCESS_KEY || !SECRET_KEY) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: "API keys not configured" }),
    };
  }

  const params = event.queryStringParameters || {};
  const action = params.action;

  try {
    let result;

    if (action === "search") {
      const keyword = encodeURIComponent(params.keyword || "");
      const limit = params.limit || 5;
      const path = `/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword=${keyword}&limit=${limit}`;
      result = await coupangApi("GET", path);
    } else if (action === "goldbox") {
      const limit = params.limit || 10;
      const path = `/v2/providers/affiliate_open_api/apis/openapi/products/goldbox?limit=${limit}`;
      result = await coupangApi("GET", path);
    } else if (action === "deeplink") {
      const body = JSON.parse(event.body || "{}");
      const path =
        "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink";
      result = await coupangApi("POST", path, body);
    } else {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          error: "action required: search, goldbox, or deeplink",
        }),
      };
    }

    return { statusCode: 200, headers, body: JSON.stringify(result) };
  } catch (err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
