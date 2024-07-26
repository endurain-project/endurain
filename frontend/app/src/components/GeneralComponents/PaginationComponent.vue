<template>
    <nav aria-label="Page navigation example">
        <ul class="pagination justify-content-center">
            <li class="page-item" :class="{ 'disabled': pageNumber == 1 }">
                <a class="page-link" @click="setPageNumber(1)">&laquo;</a>
            </li>
            <li class="page-item" v-for="page in totalPages" :key="page" :class="{ 'active': page == pageNumber }">
                <a class="page-link" @click="setPageNumber(page)">{{ page }}</a>
            </li>
            <li class="page-item" :class="{ 'disabled': pageNumber == totalPages }">
                <a class="page-link" @click="setPageNumber(totalPages)">&raquo;</a>
            </li>
        </ul>
    </nav>
</template>

<script>
import { computed } from 'vue';

export default {
    props: {
        totalPages: {
            type: Number,
            required: true,
        },
        pageNumber: {
            type: Number,
            required: true,
        },
    },
    emits: ['pageNumberChanged'],
    setup(props, { emit }){

        function setPageNumber(pageNumber) {
            emit('pageNumberChanged', pageNumber);
        }

        return {
            totalPages: computed(() => props.totalPages),
            pageNumber: computed(() => props.pageNumber),
            setPageNumber,
        }
    },
};

</script>