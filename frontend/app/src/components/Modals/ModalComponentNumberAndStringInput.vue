<template>
    <div class="modal fade" :id="`${modalId}`" tabindex="-1" :aria-labelledby="`${modalId}`" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" :id="`${modalId}`">{{ title }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <!-- number field -->
                    <label for="numberToEmit"><b>* {{ numberFieldLabel }}</b></label>
                    <input class="form-control" type="number" name="numberToEmit" :placeholder="`${numberFieldLabel}`" v-model="numberToEmit" required>
                    <!-- string field -->
                    <label for="stringToEmit"><b>* {{ stringFieldLabel }}</b></label>
                    <input class="form-control" type="text" name="stringToEmit" :placeholder="`${stringFieldLabel}`" v-model="stringToEmit" required>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                    <a type="button" @click="submitAction()" class="btn" :class="{ 'btn-success': actionButtonType === 'success', 'btn-danger': actionButtonType === 'danger', 'btn-warning': actionButtonType === 'warning', 'btn-primary': actionButtonType === 'loading'  }" data-bs-dismiss="modal">{{ actionButtonText }}</a>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref} from 'vue';

export default {
    props: {
        modalId: {
            type: String,
            required: true,
        },
        title: {
            type: String,
            required: true,
        },
        numberFieldLabel: {
            type: String,
            required: true,
        },
        numberDefaultValue: {
            type: Number,
            default: 7,
        },
        stringFieldLabel: {
            type: String,
            required: true,
        },
        stringDefaultValue: {
            type: String,
            default: '',
        },
        actionButtonType: {
            type: String,
            required: true,
        },
        actionButtonText: {
            type: String,
            required: true,
        },
    },
    emits: ['fieldsToEmitAction'],
    setup(props, { emit }) {
        const numberToEmit = ref(props.numberDefaultValue);
        const stringToEmit = ref(props.stringDefaultValue);

        function submitAction() {
            emit('fieldsToEmitAction', {
                "numberToEmit": numberToEmit.value,
                "stringToEmit": stringToEmit.value,
            });
        }

        return {
            numberToEmit,
            stringToEmit,
            submitAction,
        };
    },
};
</script>