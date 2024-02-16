import {useSignal} from "@preact/signals"
import {useEffect, type DependencyList} from "react"
import type {ReprocaMethodResponse} from ".."

export function useMethodSignal<T>(
    method: () => Promise<ReprocaMethodResponse<T>>,
    deps?: DependencyList,
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
