import type { Schemas } from '@/types'

/**
 * Raw notification payload from the backend: one shape per kind of notification,
 * told apart by `type`, each with the `options` its kind stores. Snake-cased and
 * nullable fields mirror the API exactly; never consume this shape in components
 * — map it to {@link Notification} at the service boundary.
 */
export type NotificationDto =
  | Schemas['ActivityNotificationRead']
  | Schemas['UserReferenceNotificationRead']
  | Schemas['AccountNoticeNotificationRead']
  | Schemas['StravaTokenExpiredNotificationRead']
  | Schemas['IdpLinkedNotificationRead']
  | Schemas['AccountSecurityChangedNotificationRead']
  | Schemas['NewDeviceSignInNotificationRead']

/** What a notification is about, as the backend names it. */
export type NotificationType = NotificationDto['type']

/** What every notification carries, whatever its type. */
interface NotificationBase {
  /** Stable unique identifier. */
  id: number
  /** Whether the notification has been read. */
  read: boolean
  /** ISO creation timestamp. */
  createdAt: string
  /** Owning user's id. */
  userId: number
}

/**
 * A notification as consumed by the app: a clean, camel-cased model decoupled
 * from the backend wire format so an API change is absorbed by the mapper
 * instead of rippling across the UI. `type` decides the shape of `options`.
 */
export type Notification = NotificationBase &
  (NotificationDto extends infer Dto
    ? Dto extends { type: infer Type; options: infer Options }
      ? { type: Type; options: Options }
      : never
    : never)

/** The options a notification of the given type stores. */
export type NotificationOptionsOf<Type extends NotificationType> =
  Notification extends infer Variant
    ? Variant extends { type: infer VariantType; options: infer Options }
      ? Type extends VariantType
        ? Options
        : never
      : never
    : never
