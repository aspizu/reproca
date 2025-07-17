export let apiPrefix = "/"
async function callApi<T>(name: string, parameters: any): Promise<T> {
    const response = await fetch(`${apiPrefix}${name}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(parameters),
        credentials: "include",
    })
    if (!response.ok) throw new Error(await response.text())
    return await response.json()
}

export async function function_name(
    parameters: FunctionNameParameters
): Promise<number> {
    return callApi<number>("function-name", parameters)
}

export interface FunctionNameParameters {
    param_name: number
}
