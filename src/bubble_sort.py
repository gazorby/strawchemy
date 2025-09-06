from typing import List, Union


def sorter(arr: Union[List[int], List[float]]) -> Union[List[int], List[float]]:
    n = len(arr)
    for i in range(len(arr)):
        swapped = False
        for j in range(n - 1):
            if arr[j] > arr[j + 1]:
                temp = arr[j]
                arr[j] = arr[j + 1]
                arr[j + 1] = temp
                swapped = True
        if not swapped:
            break
        n -= 1
    return arr
