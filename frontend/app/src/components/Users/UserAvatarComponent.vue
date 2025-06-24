<template>
    <img :src="userPhotoUrl" :alt="altText" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-if="user && user.photo_path">
    <img src="/src/assets/avatar/male1.png" alt="Default Female Avatar" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-else-if="(user && !user.photo_path && user.gender === 1) || !user">
    <img src="/src/assets/avatar/female1.png" alt="Default Male Avatar" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-else-if="(user && !user.photo_path && user.gender === 2) || !user">
    <img src="/src/assets/avatar/unspecified1.png" alt="Default Unspecified Avatar" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-else>
</template>
  
<script>
import { ref } from 'vue';
  
export default {
    props: {
        user: {
            type: [Object, null],
            required: true
        },
        width: {
            type: Number,
            required: true
        },
        height: {
            type: Number,
            required: true
        },
        alignTop: {
            type: Number,
            default: 1,
            required: false
        }
    },
    emits: ['userDeleted'],
    setup(props) {
        const altText = ref('User Avatar');
        const userPhotoUrl = ref(props.user?.photo_path ? `${window.env.ENDURAIN_HOST}/${props.user.photo_path}` : null);
        const alignTopValue = ref(props.alignTop);

        return {
            altText,
            userPhotoUrl,
            alignTopValue,
        };
    },
}; 
</script>