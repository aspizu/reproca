import type {Inputs} from "preact/hooks"
import {useEffect, useState} from "preact/hooks"
import type {ReprocaMethodResponse} from ".."

export function useMethod<T>(
    method: () => Promise<ReprocaMethodResponse<T>>,
    deps?: Inputs,
    {reload}: {reload?: number} = {}
) {
    const [state, setState] = useState<ReprocaMethodResponse<T> | undefined>(undefined)
    function fetch() {
        method().then(async (value) => {
            setState(value)
            if (reload && value.err) {
                const id = setTimeout(fetch, reload)
                return () => clearTimeout(id)
            }
            return undefined
        })
    }
    useEffect(fetch, deps)
    return [state, fetch] as const
}
