import {useSignal} from "@preact/signals"
import {useEffect, type Inputs} from "preact/hooks"
import type {ReprocaMethodResponse} from ".."

export function useMethodSignal<T>(
    method: () => Promise<ReprocaMethodResponse<T>>,
    deps?: Inputs,
    {reload}: {reload?: number} = {}
) {
    const state = useSignal<ReprocaMethodResponse<T> | undefined>(undefined)
    function fetch() {
        method().then(async (value) => {
            state.value = value
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
