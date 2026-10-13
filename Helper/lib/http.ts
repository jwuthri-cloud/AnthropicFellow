import { NextRequest, NextResponse } from "next/server";
import { ZodError } from "zod";
import { StoreError } from "./store";
import { runInWorkspace } from "./workspaces";

export function inWorkspace<T>(request: NextRequest, fn: () => T): T {
  guard(request);
  return runInWorkspace(
    request.nextUrl.searchParams.get("workspaceId") || undefined,
    fn,
  );
}

export function guard(request: NextRequest) {
  const hostname = request.nextUrl.hostname;
  const host = request.headers.get("host")?.split(":")[0];
  if (
    !["localhost", "127.0.0.1"].includes(hostname) ||
    !host ||
    !["localhost", "127.0.0.1"].includes(host)
  )
    throw new StoreError("Parallax is local-only", 403);
  const origin = request.headers.get("origin");
  if (
    origin &&
    origin !== request.nextUrl.origin &&
    origin !== `http://${request.headers.get("host")}`
  )
    throw new StoreError("Cross-origin requests are not allowed", 403);
  if (request.headers.get("sec-fetch-site") === "cross-site")
    throw new StoreError("Cross-site requests are not allowed", 403);
}
export function errorResponse(error: unknown) {
  if (error instanceof ZodError)
    return NextResponse.json(
      {
        error: error.issues
          .map((i) => `${i.path.join(".")}: ${i.message}`)
          .join("; "),
      },
      { status: 400 },
    );
  if (error instanceof StoreError)
    return NextResponse.json(
      { error: error.message },
      { status: error.status },
    );
  if (error instanceof SyntaxError)
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  console.error(error);
  return NextResponse.json(
    { error: "Could not complete this operation. Check the local server log." },
    { status: 500 },
  );
}
export async function jsonBody(request: NextRequest) {
  const raw = await request.text();
  if (Buffer.byteLength(raw) > 2 * 1024 * 1024)
    throw new StoreError("Request is too large", 413);
  return JSON.parse(raw);
}
