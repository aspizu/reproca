export class ReprocaUnauthorizedError extends Error {}
export class ReprocaServerError extends Error {}
export class ReprocaProtocolError extends Error {}

export type ReprocaMethodResponse<T> =
  | {
      ok: T;
      err?: never;
    }
  | {
      ok?: never;
      err: Error;
    };

export class Reproca {
  host: string;
  constructor(host: string) {
    this.host = host;
  }

  async call_method(
    path: string,
    params: object,
  ): Promise<ReprocaMethodResponse<any>> {
    let response: Response;
    try {
      response = await fetch(this.host + path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(params),
      });
    } catch (e) {
      if (e instanceof TypeError) {
        return { err: e };
      }
      throw e;
    }
    if (response.ok) {
      return { ok: await response.json() };
    }
    if (response.status === 400) {
      return { err: new ReprocaProtocolError() };
    }
    if (response.status === 401) {
      return { err: new ReprocaUnauthorizedError() };
    }
    return { err: new ReprocaServerError() };
  }

  async logout(): Promise<Response> {
    return await fetch(this.host + "/logout", { method: "POST" });
  }
}

export default function reproca(options: { host: string }): Reproca;
export default function reproca(host: string): Reproca;
export default function reproca(
  host_or_options: string | { host: string },
): Reproca {
  if (typeof host_or_options === "string") {
    return new Reproca(host_or_options);
  } else {
    return new Reproca(host_or_options.host);
  }
}
