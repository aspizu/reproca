import type {DependencyList} from "react"
import {useEffect, useState} from "react"
import type {ReprocaMethodResponse} from ".."

export function useMethod<T>(
    method: () => Promise<ReprocaMethodResponse<T>>,
    deps?: DependencyList,
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
