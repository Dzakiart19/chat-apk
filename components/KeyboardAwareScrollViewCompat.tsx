import { Platform, ScrollView, ScrollViewProps } from "react-native";

type Props = ScrollViewProps & {
  keyboardShouldPersistTaps?: "always" | "never" | "handled";
  bottomOffset?: number;
  disableScrollOnKeyboardHide?: boolean;
};

export function KeyboardAwareScrollViewCompat({
  children,
  keyboardShouldPersistTaps = "handled",
  bottomOffset,
  disableScrollOnKeyboardHide,
  ...props
}: Props) {
  if (Platform.OS === "web") {
    return (
      <ScrollView keyboardShouldPersistTaps={keyboardShouldPersistTaps} {...props}>
        {children}
      </ScrollView>
    );
  }

  const {
    KeyboardAwareScrollView,
  } = require("react-native-keyboard-controller");

  return (
    <KeyboardAwareScrollView
      keyboardShouldPersistTaps={keyboardShouldPersistTaps}
      bottomOffset={bottomOffset}
      disableScrollOnKeyboardHide={disableScrollOnKeyboardHide}
      {...props}
    >
      {children}
    </KeyboardAwareScrollView>
  );
}
