<template>
    <nav aria-label="Page navigation example">
        <ul class="pagination justify-content-center">
            <li class="page-item" :class="{ 'disabled': pageNumber == 1 }">
                <a class="page-link" @click="setPageNumber(1)">&laquo;</a>
            </li>
            <template v-for="(page, index) in pagesToShow" :key="page === '...' ? `ellipsis_${index}` : page">
                <li v-if="page === '...'" class="page-item disabled">
                    <span class="page-link">...</span>
                </li>
                <li v-else class="page-item" :class="{ 'active': page == pageNumber }">
                    <a class="page-link" @click="setPageNumber(page)">{{ page }}</a>
                </li>
            </template>
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
    setup(props, { emit }) {
        const pagesToShow = computed(() => {
            const pages = [];
            const currentPage = props.pageNumber;
            const lastPage = props.totalPages;

            // If less than or equal to 10 pages, show all
            if (lastPage <= 10) {
                return Array.from({ length: lastPage }, (_, i) => i + 1);
            }

            // Calculate tens (10, 20, 30, etc.)
            const tens = [];
            for (let i = 10; i < lastPage; i += 10) {
                tens.push(i);
            }

            if (currentPage <= 2) {
                // First few pages selected (1-3)
                pages.push(1, 2, 3);
                pages.push('...');
                for (const ten of tens) {
                    if (ten < lastPage - 3) {
                        pages.push(ten);
                        pages.push('...');
                    }
                }
                pages.push(lastPage);
            } else if (currentPage >= lastPage - 1) {
                // Last few pages selected
                pages.push(1, '...');
                for (const ten of tens) {
                    if (ten < lastPage - 3) {
                        pages.push(ten);
                        pages.push('...');
                    }
                }
                pages.push(lastPage - 2, lastPage - 1, lastPage);
            } else {
                // Middle pages
                pages.push(1, '...');
                // Add tens before current page
                for (const ten of tens) {
                    if (ten < currentPage - 1) {
                        pages.push(ten);
                        pages.push('...');
                    }
                }
                pages.push(currentPage - 1, currentPage, currentPage + 1);
                if (currentPage + 1 < lastPage - 1) {
                    pages.push('...');
                }
                // Add tens after current page but before last page
                for (const ten of tens) {
                    if (ten > currentPage + 1 && ten < lastPage) {
                        pages.push(ten);
                        pages.push('...');
                    }
                }
                pages.push(lastPage);
            }

            return pages;
        });

        function setPageNumber(pageNumber) {
            emit('pageNumberChanged', pageNumber);
        }

        return {
            pagesToShow,
            setPageNumber,
        }
    },
};
</script>